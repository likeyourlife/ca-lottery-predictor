/**
 * California Fantasy 5 Prediction Engines - Pure JS Implementation
 * 纯浏览器端运行的预测引擎, 不依赖后端
 * 
 * 引擎对应:
 * - E1 频次偏差 (8%)  → FrequencyEngine
 * - E2 贝叶斯 (22%)   → BayesianEngine
 * - E3 马尔可夫 (36%)  → MarkovEngine
 * - E4 连号联合 (34%)  → JointEngine
 * - E5 FFT周期 (1%)   → FFTEngine (简化DFT)
 * - E6 蒙特卡洛 (0%)  → 跳过
 * 
 * 数据格式: draw_data.json = [{d:"2022-01-01",n:[2,5,25,26,38]}, ...]
 */

// ── Constants ──
const POOL_SIZE = 39;
const DRAW_COUNT = 5;
const THEORETICAL_PROB = 5 / 39;    // ≈ 0.1282
const THEORETICAL_LOW = 34 / 39;    // ≈ 0.8718
const NUMBER_POOL = Array.from({length: 39}, (_, i) => i + 1);

// 引擎权重 (回测驱动优化 v2)
const ENGINE_WEIGHTS = {
    freq: 0.08,
    bayesian: 0.22,
    markov: 0.36,
    joint: 0.34,
    fft: 0.01,
};

// 贝叶斯先验
const BAYESIAN_PRIOR_WEIGHT = 50;
const ALPHA0 = THEORETICAL_PROB * BAYESIAN_PRIOR_WEIGHT;   // ≈ 6.41
const BETA0 = THEORETICAL_LOW * BAYESIAN_PRIOR_WEIGHT;     // ≈ 43.59

// 回补策略
const REBOUND_BONUS_PER_DRAW = 0.002;
const REBOUND_WINDOW = 10;


// ── Utility Functions ──

function erf(x) {
    /** 近似误差函数 (Abramowitz & Stegun) */
    const a1 = 0.254829592, a2 = -0.284496736, a3 = 1.421413741;
    const a4 = -1.453152027, a5 = 1.061405429, p = 0.3275911;
    const sign = x < 0 ? -1 : 1;
    x = Math.abs(x);
    const t = 1.0 / (1.0 + p * x);
    const y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-x * x);
    return sign * y;
}

function zToProb(z) {
    /** Z-score → Φ(z) (标准正态CDF) */
    return 0.5 * (1 + erf(z / Math.sqrt(2)));
}


// ── E1: Frequency Engine ──

class FrequencyEngine {
    compute(records) {
        const freq = this._buildFreqTable(records);
        const N = records.length;
        const expected = N * THEORETICAL_PROB;
        const sigma = Math.sqrt(N * THEORETICAL_PROB * (1 - THEORETICAL_PROB));
        
        const results = {};
        for (const n of NUMBER_POOL) {
            const observed = freq[n] || 0;
            const z = sigma > 0 ? (observed - expected) / sigma : 0;
            const pAppear = zToProb(z);
            // 限制在合理范围
            const pAppearClamped = Math.max(THEORETICAL_PROB * 0.3, Math.min(THEORETICAL_PROB * 3.0, pAppear));
            const pLow = 1 - pAppearClamped;
            
            results[n] = {
                observed_freq: observed,
                expected_freq: Math.round(expected * 100) / 100,
                z_score: Math.round(z * 10000) / 10000,
                p_appear: Math.round(pAppearClamped * 10000) / 10000,
                p_low: Math.round(pLow * 10000) / 10000,
            };
        }
        return results;
    }
    
    _buildFreqTable(records) {
        const freq = {};
        for (const n of NUMBER_POOL) freq[n] = 0;
        for (const r of records) {
            for (const num of r.n) {
                if (freq[num] !== undefined) freq[num]++;
            }
        }
        return freq;
    }
}


// ── E2: Bayesian Engine ──

class BayesianEngine {
    compute(records) {
        const freq = new FrequencyEngine()._buildFreqTable(records);
        const N = records.length;
        
        const results = {};
        for (const n of NUMBER_POOL) {
            const k = freq[n] || 0;
            const alphaPost = ALPHA0 + k;
            const betaPost = BETA0 + (N - k);
            const pAppear = alphaPost / (alphaPost + betaPost);
            const pLow = 1 - pAppear;
            
            // 95% CI (正态近似)
            const total = alphaPost + betaPost;
            const mean = alphaPost / total;
            const var_ = alphaPost * betaPost / (total * total * (total + 1));
            const std = Math.sqrt(var_);
            const lower = Math.max(0, mean - 1.96 * std);
            const upper = Math.min(1, mean + 1.96 * std);
            
            results[n] = {
                k: k,
                alpha_post: Math.round(alphaPost * 10000) / 10000,
                beta_post: Math.round(betaPost * 10000) / 10000,
                p_appear: Math.round(pAppear * 10000) / 10000,
                p_low: Math.round(pLow * 10000) / 10000,
                credible_lower: Math.round(lower * 10000) / 10000,
                credible_upper: Math.round(upper * 10000) / 10000,
            };
        }
        return results;
    }
}


// ── E3: Markov Engine ──

class MarkovEngine {
    compute(records) {
        if (records.length < 3) return this._defaultResults();
        
        const presence = this._buildPresenceSeries(records);
        const N = records.length;
        const lastSet = new Set(records[N - 1].n);
        
        const results = {};
        for (const n of NUMBER_POOL) {
            const series = presence[n];
            
            // 统计转移次数
            let aa = 0, am = 0, ma = 0, mm = 0;
            for (let t = 1; t < N; t++) {
                const prev = series[t - 1], curr = series[t];
                if (prev === 1 && curr === 1) aa++;
                else if (prev === 1 && curr === 0) am++;
                else if (prev === 0 && curr === 1) ma++;
                else mm++;
            }
            
            // Laplace 平滑
            const smoothing = 1.0;
            const totalFromAppear = aa + am + smoothing * 2;
            const totalFromMiss = ma + mm + smoothing * 2;
            
            const pAppearAfterAppear = (aa + smoothing) / totalFromAppear;
            const pAppearAfterMiss = (ma + smoothing) / totalFromMiss;
            
            const lastState = lastSet.has(n) ? 'appear' : 'miss';
            const pAppear = lastState === 'appear' ? pAppearAfterAppear : pAppearAfterMiss;
            const pLow = 1 - pAppear;
            
            // 信号分类
            let signal = 'neutral';
            if (pAppearAfterAppear > THEORETICAL_PROB * 1.3) signal = 'hot';
            else if (pAppearAfterMiss < THEORETICAL_PROB * 0.7) signal = 'cold';
            
            results[n] = {
                transition_appear_after_appear: Math.round(pAppearAfterAppear * 10000) / 10000,
                transition_appear_after_miss: Math.round(pAppearAfterMiss * 10000) / 10000,
                last_state: lastState,
                p_appear: Math.round(pAppear * 10000) / 10000,
                p_low: Math.round(pLow * 10000) / 10000,
                markov_signal: signal,
            };
        }
        return results;
    }
    
    _buildPresenceSeries(records) {
        const series = {};
        for (const n of NUMBER_POOL) series[n] = [];
        for (const r of records) {
            const numSet = new Set(r.n);
            for (const n of NUMBER_POOL) {
                series[n].push(numSet.has(n) ? 1 : 0);
            }
        }
        return series;
    }
    
    _defaultResults() {
        const results = {};
        for (const n of NUMBER_POOL) {
            results[n] = {
                p_appear: Math.round(THEORETICAL_PROB * 10000) / 10000,
                p_low: Math.round(THEORETICAL_LOW * 10000) / 10000,
                markov_signal: 'neutral',
            };
        }
        return results;
    }
}


// ── E4: Joint (Co-occurrence) Engine ──

class JointEngine {
    compute(records) {
        if (records.length < 20) return this._defaultResults();
        
        const N = records.length;
        const coMatrix = this._buildCoMatrix(records);
        
        // 理论共现期望
        const expectedCoProb = THEORETICAL_PROB * ((DRAW_COUNT - 1) / (POOL_SIZE - 1));
        const expectedCoCount = N * expectedCoProb;
        
        const results = {};
        for (const n of NUMBER_POOL) {
            let exclusionScore = 0, coOccurrenceScore = 0;
            
            for (const other of NUMBER_POOL) {
                if (other === n) continue;
                const key = `${Math.min(n, other)},${Math.max(n, other)}`;
                const actual = coMatrix[key] || 0;
                const deviation = (actual - expectedCoCount) / Math.max(expectedCoCount, 1);
                
                if (deviation < 0) {
                    exclusionScore += Math.abs(deviation);
                } else {
                    coOccurrenceScore += deviation;
                }
            }
            
            const jointSignal = exclusionScore - coOccurrenceScore;
            const normalized = jointSignal / 38.0;
            const pLowAdjustment = 0.05 * Math.tanh(normalized * 2);
            const pLow = THEORETICAL_LOW + pLowAdjustment;
            const pLowClamped = Math.max(0.80, Math.min(0.95, pLow));
            
            results[n] = {
                exclusion_score: Math.round(exclusionScore * 10000) / 10000,
                co_occurrence_score: Math.round(coOccurrenceScore * 10000) / 10000,
                p_low: Math.round(pLowClamped * 10000) / 10000,
                p_appear: Math.round((1 - pLowClamped) * 10000) / 10000,
            };
        }
        return results;
    }
    
    _buildCoMatrix(records) {
        const coMatrix = {};
        for (const r of records) {
            const nums = r.n;
            for (let i = 0; i < nums.length; i++) {
                for (let j = i + 1; j < nums.length; j++) {
                    const key = `${nums[i]},${nums[j]}`;
                    coMatrix[key] = (coMatrix[key] || 0) + 1;
                }
            }
        }
        return coMatrix;
    }
    
    _defaultResults() {
        const results = {};
        for (const n of NUMBER_POOL) {
            results[n] = { p_low: Math.round(THEORETICAL_LOW * 10000) / 10000, p_appear: Math.round(THEORETICAL_PROB * 10000) / 10000 };
        }
        return results;
    }
}


// ── E5: FFT Engine (简化 DFT) ──

class FFTEngine {
    compute(records) {
        if (records.length < 30) return this._defaultResults();
        
        const presence = new MarkovEngine()._buildPresenceSeries(records);
        const N = records.length;
        const checkPeriods = [5, 7, 10, 14, 20, 30];
        
        const results = {};
        for (const n of NUMBER_POOL) {
            const series = presence[n];
            
            let bestPeriod = 0, bestAmplitude = 0, bestPhase = 0;
            for (const period of checkPeriods) {
                let cosSum = 0, sinSum = 0;
                for (let t = 0; t < N; t++) {
                    const angle = 2 * Math.PI * t / period;
                    cosSum += series[t] * Math.cos(angle);
                    sinSum += series[t] * Math.sin(angle);
                }
                const amplitude = Math.sqrt(cosSum ** 2 + sinSum ** 2) / N;
                const phase = Math.atan2(sinSum, cosSum);
                
                if (amplitude > bestAmplitude) {
                    bestAmplitude = amplitude;
                    bestPeriod = period;
                    bestPhase = phase;
                }
            }
            
            const cyclePhase = ((bestPhase / (2 * Math.PI)) % 1.0 + 1.0) % 1.0;
            let cyclePosition = 'transition';
            if ((cyclePhase >= 0 && cyclePhase < 0.25) || cyclePhase >= 0.9) cyclePosition = 'peak';
            else if (cyclePhase >= 0.5 && cyclePhase < 0.75) cyclePosition = 'valley';
            
            // 周期性强度
            const totalVariance = series.reduce((s, x) => s + (x - THEORETICAL_PROB) ** 2, 0) / N;
            const periodicityStrength = totalVariance > 0 ? Math.min(bestAmplitude / Math.sqrt(totalVariance), 1.0) : 0;
            
            const positionFactor = {peak: -0.03, transition: 0, valley: 0.03};
            const adjustment = (positionFactor[cyclePosition] || 0) * periodicityStrength;
            
            const pLow = THEORETICAL_LOW + adjustment;
            const pLowClamped = Math.max(0.80, Math.min(0.95, pLow));
            
            results[n] = {
                dominant_period: bestPeriod,
                cycle_phase: Math.round(cyclePhase * 10000) / 10000,
                cycle_position: cyclePosition,
                periodicity_strength: Math.round(periodicityStrength * 10000) / 10000,
                p_low: Math.round(pLowClamped * 10000) / 10000,
                p_appear: Math.round((1 - pLowClamped) * 10000) / 10000,
            };
        }
        return results;
    }
    
    _defaultResults() {
        const results = {};
        for (const n of NUMBER_POOL) {
            results[n] = { p_low: Math.round(THEORETICAL_LOW * 10000) / 10000, p_appear: Math.round(THEORETICAL_PROB * 10000) / 10000 };
        }
        return results;
    }
}


// ── Fusion Engine ──

class FusionEngine {
    constructor() {
        this.engines = {
            freq: new FrequencyEngine(),
            bayesian: new BayesianEngine(),
            markov: new MarkovEngine(),
            joint: new JointEngine(),
            fft: new FFTEngine(),
        };
    }
    
    computeFusion(records) {
        const engineResults = {};
        for (const [eid, engine] of Object.entries(this.engines)) {
            engineResults[eid] = engine.compute(records);
        }
        
        const totalWeight = Object.values(ENGINE_WEIGHTS).reduce((a, b) => a + b, 0);
        
        const fusion = {};
        for (const n of NUMBER_POOL) {
            let pLowFusion = 0;
            const detail = {};
            
            for (const [eid, weight] of Object.entries(ENGINE_WEIGHTS)) {
                const pLow = engineResults[eid]?.[n]?.p_low ?? THEORETICAL_LOW;
                pLowFusion += weight * pLow;
                detail[`p_low_${eid}`] = pLow;
            }
            
            if (totalWeight > 0) pLowFusion /= totalWeight;
            
            // 一致性指标
            const pLowValues = Object.entries(ENGINE_WEIGHTS).map(([eid]) => detail[`p_low_${eid}`]);
            const mean = pLowValues.reduce((a, b) => a + b, 0) / pLowValues.length;
            const variance = pLowValues.reduce((s, v) => s + (v - mean) ** 2, 0) / pLowValues.length;
            const consistency = 1 - Math.min(variance * 10, 1.0);
            
            fusion[n] = {
                ...detail,
                p_low_fusion: Math.round(pLowFusion * 10000) / 10000,
                p_appear_fusion: Math.round((1 - pLowFusion) * 10000) / 10000,
                engine_consistency: Math.round(consistency * 10000) / 10000,
            };
        }
        
        return fusion;
    }
    
    getAvoidRanking(records) {
        const fusion = this.computeFusion(records);
        const ranking = NUMBER_POOL.map(n => [n, fusion[n].p_low_fusion]);
        ranking.sort((a, b) => b[1] - a[1]);  // P_low最高排最前
        return ranking;
    }
    
    getReboundRanking(records) {
        const fusion = this.computeFusion(records);
        const currentGaps = this._computeCurrentGaps(records);
        const recentFreq = this._buildRecentFreq(records);
        
        const ranking = [];
        for (const n of NUMBER_POOL) {
            const pLowBase = fusion[n].p_low_fusion;
            const gap = currentGaps[n] || 0;
            const recentCount = recentFreq[n] || 0;
            
            const gapBonus = gap * REBOUND_BONUS_PER_DRAW;
            const coldBonus = recentCount === 0 ? REBOUND_WINDOW * REBOUND_BONUS_PER_DRAW * 0.5 : 0;
            
            const pLowRebound = pLowBase + gapBonus + coldBonus;
            ranking.push([n, Math.round(pLowRebound * 10000) / 10000, {
                p_low_base: pLowBase,
                gap: gap,
                recent_count: recentCount,
                gap_bonus: Math.round(gapBonus * 10000) / 10000,
                cold_bonus: Math.round(coldBonus * 10000) / 10000,
            }]);
        }
        
        ranking.sort((a, b) => b[1] - a[1]);
        return ranking;
    }
    
    _computeCurrentGaps(records) {
        const N = records.length;
        const gaps = {};
        for (const n of NUMBER_POOL) {
            let gap = 0;
            for (let i = N - 1; i >= 0; i--) {
                if (records[i].n.includes(n)) {
                    gap = N - 1 - i;
                    break;
                }
            }
            gaps[n] = gap;
        }
        return gaps;
    }
    
    _buildRecentFreq(records) {
        const recent = records.slice(-REBOUND_WINDOW);
        const freq = {};
        for (const n of NUMBER_POOL) freq[n] = 0;
        for (const r of recent) {
            for (const num of r.n) freq[num]++;
        }
        return freq;
    }
    
    getTopN(level, mode, records) {
        if (mode === 'avoid') {
            const ranking = this.getAvoidRanking(records);
            return ranking.slice(0, level);
        } else {
            const ranking = this.getReboundRanking(records);
            return ranking.slice(0, level);
        }
    }
}


// ── Main Prediction Function ──

function runJSPrediction(drawData) {
    /**
     * 在浏览器端运行完整预测管线
     * 输入: drawData = [{d:"2022-01-01",n:[2,5,25,26,38]}, ...]
     * 输出: 与 generate_api_data.py 相同结构的 prediction.json
     */
    const fusion = new FusionEngine();
    const N = drawData.length;
    const lastDate = drawData[N - 1]?.d || '';
    
    const result = {
        generated_at: new Date().toISOString(),
        game: 'Fantasy 5',
        number_range: '1-39',
        draw_count: 5,
        data_count: N,
        last_draw_date: lastDate,
        confidence: 'B (统计级, 非因果级)',
        disclaimer: '本软件不声称能预测彩票中奖号码。彩票开奖本质为随机过程，模型输出的概率排序仅为统计参考，不构成投注建议。',
        weights: ENGINE_WEIGHTS,
        avoid: {},
        rebound: {},
    };
    
    for (const level of [2, 4, 10]) {
        const avoidTop = fusion.getTopN(level, 'avoid', drawData);
        result.avoid[`top${level}`] = avoidTop.map(([num, pLow]) => ({
            number: num,
            p_low: pLow,
        }));
        
        const reboundTop = fusion.getTopN(level, 'rebound', drawData);
        result.rebound[`top${level}`] = reboundTop.map(([num, pLowRebound, detail]) => ({
            number: num,
            p_low: pLowRebound,
            gap: detail.gap,
            gap_bonus: detail.gap_bonus,
        }));
    }
    
    return result;
}

function computeConsecutiveAbsence(drawData) {
    /** 计算每个号码连续不中奖期数 */
    const N = drawData.length;
    const absence = {};
    for (const n of NUMBER_POOL) {
        let gap = 0;
        for (let i = N - 1; i >= 0; i--) {
            if (drawData[i].n.includes(n)) {
                gap = N - 1 - i;
                break;
            }
        }
        absence[n] = gap;
    }
    return absence;
}

function computeDailyAccuracy(drawData) {
    /** 简化版: 用最近30期的逐期回测 */
    const N = drawData.length;
    const window = 30;
    if (N < window + 60) return [];
    
    const fusion = new FusionEngine();
    const accuracy = [];
    
    // 从最近30期开始, 每期用之前所有数据做预测
    for (let i = N - window; i < N; i++) {
        const trainData = drawData.slice(0, i);  // 用之前的全部数据训练
        const actualNums = drawData[i].n;
        
        const avoidTop2 = fusion.getTopN(2, 'avoid', trainData).map(([n]) => n);
        const avoidTop4 = fusion.getTopN(4, 'avoid', trainData).map(([n]) => n);
        const avoidTop10 = fusion.getTopN(10, 'avoid', trainData).map(([n]) => n);
        
        const top2Hit = avoidTop2.some(n => actualNums.includes(n));
        const top4Hit = avoidTop4.some(n => actualNums.includes(n));
        const top10Hit = avoidTop10.some(n => actualNums.includes(n));
        
        accuracy.push({
            date: drawData[i].d,
            top2_hit: top2Hit,
            top4_hit: top4Hit,
            top10_hit: top10Hit,
        });
    }
    
    return accuracy;
}

function computeRecentDraws(drawData) {
    /** 最近10期开奖 + 预测对比 */
    const N = drawData.length;
    if (N < 70) return [];  // 需要足够数据
    
    const fusion = new FusionEngine();
    const recent = [];
    
    // 最近10期, 每期用之前的数据做预测
    for (let i = N - 10; i < N; i++) {
        const trainData = drawData.slice(0, i);
        const actualNums = drawData[i].n;
        
        const avoidTop2 = fusion.getTopN(2, 'avoid', trainData).map(([n]) => n);
        const avoidTop4 = fusion.getTopN(4, 'avoid', trainData).map(([n]) => n);
        const avoidTop10 = fusion.getTopN(10, 'avoid', trainData).map(([n]) => n);
        
        const top2Hit = avoidTop2.some(n => actualNums.includes(n));
        const top4Hit = avoidTop4.some(n => actualNums.includes(n));
        const top10Hit = avoidTop10.some(n => actualNums.includes(n));
        
        recent.push({
            date: drawData[i].d,
            winning_numbers: actualNums,
            top2_avoid: avoidTop2,
            top4_avoid: avoidTop4,
            top10_avoid: avoidTop10,
            top2_hit: top2Hit,
            top4_hit: top4Hit,
            top10_hit: top10Hit,
        });
    }
    
    return recent;
}

// ── Export for module usage ──
// (在浏览器中直接通过 script tag 加载, 全局可用)
