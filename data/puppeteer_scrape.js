#!/usr/bin/env node
/**
 * Puppeteer 数据抓取脚本 - 从 california.lottonumbers.com 抓取 Fantasy 5 历史数据
 * 
 * 目标: 补充 2022-01 到 2024-12 的完整历史数据(约730期)
 * 输出: JSON 格式 draw_data.json, 与现有数据格式兼容
 * 
 * 用法: NODE_PATH=... node puppeteer_scrape.js [--year 2022] [--year 2023] ...
 */

const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const OUTPUT_DIR = path.join(__dirname, 'scraped_data');
const BASE_URL = 'https://www.calottery.com/site-archive';

// 备用源: california.lottonumbers.com (更稳定)
const ALT_BASE_URL = 'https://california.lottonumbers.com/fantasy-5';

function parseDrawRow(row) {
    /** 从 HTML 行中提取日期和号码 */
    // 格式: 日期 + 5个号码
    const dateMatch = row.match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
    if (!dateMatch) return null;
    
    const month = parseInt(dateMatch[1]);
    const day = parseInt(dateMatch[2]);
    const year = parseInt(dateMatch[3]);
    const dateStr = `${year}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
    
    // 提取号码(1-39范围)
    const numPattern = /(\d{1,2})/g;
    const allNums = [];
    let match;
    // 从号码区域提取
    const numSection = row.replace(dateMatch[0], ''); // 去掉日期部分
    while ((match = numPattern.exec(numSection)) !== null) {
        const n = parseInt(match[1]);
        if (n >= 1 && n <= 39 && allNums.length < 5) {
            allNums.push(n);
        }
    }
    
    if (allNums.length !== 5) return null;
    
    return {
        draw_date: dateStr,
        num1: String(allNums[0]),
        num2: String(allNums[1]),
        num3: String(allNums[2]),
        num4: String(allNums[3]),
        num5: String(allNums[4]),
        jackpot_amount: '0'
    };
}


async function scrapeFromCalLottoNumbers(browser, year) {
    /** 从 california.lottonumbers.com 抓取指定年份的数据 */
    
    // 该网站按年份/月份组织数据
    const results = [];
    
    for (let month = 1; month <= 12; month++) {
        const url = `${ALT_BASE_URL}/${year}-${String(month).padStart(2, '0')}`;
        console.log(`  抓取: ${url}`);
        
        const page = await browser.newPage();
        try {
            await page.goto(url, { waitUntil: 'networkidle2', timeout: 15000 });
            
            // 等待数据表格加载
            await page.waitForSelector('table, .draw-results, .results-table, tbody', { timeout: 8000 })
                .catch(() => console.log(`    ${year}-${month} 无表格数据`));
            
            // 提取所有包含号码的行
            const draws = await page.evaluate(() => {
                const rows = document.querySelectorAll('tr, .result-row, .draw-row');
                const data = [];
                
                rows.forEach(row => {
                    const text = row.innerText;
                    // 匹配日期格式 MM/DD/YYYY 或类似
                    const dateMatch = text.match(/(\d{1,2})\/(\d{1,2})\/(\d{2,4})/);
                    if (!dateMatch) return;
                    
                    // 提取号码
                    const numCells = row.querySelectorAll('td, .ball, .number, span');
                    const nums = [];
                    numCells.forEach(cell => {
                        const n = parseInt(cell.innerText.trim());
                        if (n >= 1 && n <= 39 && nums.length < 5) {
                            nums.push(n);
                        }
                    });
                    
                    if (nums.length === 5) {
                        const month = parseInt(dateMatch[1]);
                        const day = parseInt(dateMatch[2]);
                        let year = parseInt(dateMatch[3]);
                        if (year < 100) year += 2000;
                        
                        data.push({
                            draw_date: `${year}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`,
                            num1: String(nums[0]),
                            num2: String(nums[1]),
                            num3: String(nums[2]),
                            num4: String(nums[3]),
                            num5: String(nums[4]),
                            jackpot_amount: '0'
                        });
                    }
                });
                
                return data;
            });
            
            results.push(...draws);
            console.log(`    ${year}-${String(month).padStart(2,'0')}: ${draws.length} 条`);
            
        } catch (e) {
            console.log(`    ${year}-${String(month).padStart(2,'0')} 失败: ${e.message}`);
        } finally {
            await page.close();
        }
    }
    
    return results;
}


async function scrapeFromLotteryValley(browser, year) {
    /** 从 lotteryvalley.com 抓取备用数据 */
    
    const url = `https://www.lotteryvalley.com/california/fantasy-five/past-results/?year=${year}`;
    console.log(`  抓取(lotteryvalley): ${url}`);
    
    const page = await browser.newPage();
    try {
        await page.goto(url, { waitUntil: 'networkidle2', timeout: 20000 });
        await page.waitForSelector('table, .past-results', { timeout: 10000 })
            .catch(() => {});
        
        const draws = await page.evaluate(() => {
            const rows = document.querySelectorAll('tr');
            const data = [];
            
            rows.forEach(row => {
                const text = row.innerText;
                const dateMatch = text.match(/(\d{1,2})\/(\d{1,2})\/(\d{2,4})/);
                if (!dateMatch) return;
                
                const numCells = row.querySelectorAll('td');
                const nums = [];
                numCells.forEach(cell => {
                    const n = parseInt(cell.innerText.trim());
                    if (n >= 1 && n <= 39 && nums.length < 5) {
                        nums.push(n);
                    }
                });
                
                if (nums.length === 5) {
                    const month = parseInt(dateMatch[1]);
                    const day = parseInt(dateMatch[2]);
                    let yr = parseInt(dateMatch[3]);
                    if (yr < 100) yr += 2000;
                    
                    data.push({
                        draw_date: `${yr}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`,
                        num1: String(nums[0]),
                        num2: String(nums[1]),
                        num3: String(nums[2]),
                        num4: String(nums[3]),
                        num5: String(nums[4]),
                        jackpot_amount: '0'
                    });
                }
            });
            
            return data;
        });
        
        console.log(`    lotteryvalley ${year}: ${draws.length} 条`);
        return draws;
        
    } catch (e) {
        console.log(`    lotteryvalley ${year} 失败: ${e.message}`);
        return [];
    } finally {
        await page.close();
    }
}


async function main() {
    // 解析参数
    const args = process.argv.slice(2);
    let years = [];
    
    for (let i = 0; i < args.length; i++) {
        if (args[i] === '--year' && args[i+1]) {
            years.push(parseInt(args[i+1]));
            i++;
        }
    }
    
    // 默认抓取缺失的年份
    if (years.length === 0) {
        years = [2022, 2023, 2024, 2025];
    }
    
    console.log('╔══════════════════════════════════════════╗');
    console.log('║  Puppeteer 数据抓取 - Fantasy 5         ║');
    console.log('║  目标年份: ' + years.join(', ') + '              ║');
    console.log('╚══════════════════════════════════════════╝');
    
    // 创建输出目录
    if (!fs.existsSync(OUTPUT_DIR)) {
        fs.mkdirSync(OUTPUT_DIR, { recursive: true });
    }
    
    // 启动 Puppeteer
    const browser = await puppeteer.launch({
        headless: 'new',
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu'],
    });
    
    let allDraws = [];
    
    for (const year of years) {
        console.log(`\n── 抓取 ${year} 年 ──`);
        
        // 主源: california.lottonumbers.com
        let draws = await scrapeFromCalLottoNumbers(browser, year);
        
        // 如果主源不够, 用备用源补充
        if (draws.length < 300) {
            console.log(`  主源数据不足(${draws.length}), 尝试备用源...`);
            const altDraws = await scrapeFromLotteryValley(browser, year);
            // 合并去重
            const existingDates = new Set(draws.map(d => d.draw_date));
            const newDraws = altDraws.filter(d => !existingDates.has(d.draw_date));
            draws.push(...newDraws);
        }
        
        allDraws.push(...draws);
        
        // 保存单年数据
        const yearPath = path.join(OUTPUT_DIR, `fantasy5_${year}.json`);
        fs.writeFileSync(yearPath, JSON.stringify(draws, null, 2));
        console.log(`  ${year} 年总计: ${draws.length} 条 → ${yearPath}`);
    }
    
    await browser.close();
    
    // 合并 + 去重 + 排序
    const dateSet = new Set();
    const uniqueDraws = [];
    for (const d of allDraws) {
        if (!dateSet.has(d.draw_date)) {
            dateSet.add(d.draw_date);
            uniqueDraws.push(d);
        }
    }
    uniqueDraws.sort((a, b) => a.draw_date.localeCompare(b.draw_date));
    
    // 保存完整数据
    const outputPath = path.join(OUTPUT_DIR, 'fantasy5_all_scraped.json');
    fs.writeFileSync(outputPath, JSON.stringify(uniqueDraws, null, 2));
    
    console.log('\n╔══════════════════════════════════════════╗');
    console.log(`║  抓取完成! 总计: ${uniqueDraws.length} 条               ║`);
    console.log(`║  日期范围: ${uniqueDraws[0]?.draw_date || 'N/A'} - ${uniqueDraws[uniqueDraws.length-1]?.draw_date || 'N/A'}  ║`);
    console.log(`║  输出: ${outputPath}                    ║`);
    console.log('╚══════════════════════════════════════════╝');
    
    // 与现有数据做去重比对
    try {
        const { init_fantasy5_data } = require(path.join(__dirname, '..', 'data', 'fetcher'));
        // Note: Python 模块不能直接 require, 需要单独处理
        console.log('\n⚠️  如需合并到现有数据，请运行: python data/merge_scraped_data.py');
    } catch (e) {
        // 忽略
    }
}


main().catch(e => {
    console.error('抓取失败:', e);
    process.exit(1);
});
