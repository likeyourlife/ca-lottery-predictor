#!/usr/bin/env node
/**
 * Puppeteer 数据抓取脚本 v2 - 从 california.lottonumbers.com 抓取 Fantasy 5 历史数据
 * 
 * 正确 URL: /fantasy-5/past-numbers/{year}
 * 使用 puppeteer-core + 系统 Chrome (避免下载 Chromium)
 * 
 * 用法: NODE_PATH=... node puppeteer_scrape.js [--year 2022] [--year 2023] ...
 */

const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

const OUTPUT_DIR = path.join(__dirname, 'scraped_data');
const CHROME_PATH = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

// 正确的URL格式: /fantasy-5/past-numbers/{year}
const BASE_URL = 'https://california.lottonumbers.com/fantasy-5/past-numbers';


async function scrapeYear(browser, year) {
    /** 从 california.lottonumbers.com 抓取整年数据 */
    
    const url = `${BASE_URL}/${year}`;
    console.log(`  抓取: ${url}`);
    
    const page = await browser.newPage();
    try {
        await page.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });
        
        // 等待数据区域加载
        await page.waitForSelector('ul, .draw-result, .results, tbody', { timeout: 10000 })
            .catch(() => console.log(`  ${year}: 未找到标准数据容器，尝试全页面提取`));
        
        // 给页面更多渲染时间
        await new Promise(r => setTimeout(r, 2000));
        
        // 从页面提取所有开奖数据
        const draws = await page.evaluate(() => {
            const results = [];
            const allText = document.body.innerText;
            
            // 匹配日期+号码模式
            // 日期格式: MM/DD/YYYY 或 Month DD, YYYY
            // 号码格式: 5个1-39的数字，通常在日期后面
            const lines = allText.split('\n');
            
            let currentDate = null;
            let currentNumbers = [];
            
            for (const line of lines) {
                const trimmed = line.trim();
                
                // 尝试匹配日期: MM/DD/YYYY
                const slashDate = trimmed.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
                if (slashDate) {
                    // 如果前面有完整的5个号码，保存上一组
                    if (currentDate && currentNumbers.length === 5) {
                        results.push({ date: currentDate, numbers: currentNumbers });
                    }
                    const month = parseInt(slashDate[1]);
                    const day = parseInt(slashDate[2]);
                    const yr = parseInt(slashDate[3]);
                    currentDate = `${yr}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
                    currentNumbers = [];
                    continue;
                }
                
                // 尝试匹配单个号码(1-39)
                const num = parseInt(trimmed);
                if (num >= 1 && num <= 39 && currentDate) {
                    currentNumbers.push(num);
                    if (currentNumbers.length === 5) {
                        // 可能是一组完整数据
                        // 不立即保存，等下一个日期触发保存
                    }
                }
            }
            
            // 保存最后一组
            if (currentDate && currentNumbers.length === 5) {
                results.push({ date: currentDate, numbers: currentNumbers });
            }
            
            return results;
        });
        
        // 如果简单文本提取不够，尝试DOM结构提取
        if (draws.length < 50) {
            console.log(`  ${year}: 文本提取仅${draws.length}条，尝试DOM提取...`);
            
            const domDraws = await page.evaluate(() => {
                const results = [];
                
                // 查找所有包含日期的元素
                const dateElements = document.querySelectorAll('[class*="date"], [class*="draw"], a[href*="numbers"]');
                
                dateElements.forEach(el => {
                    const text = el.innerText || el.textContent;
                    const href = el.href || '';
                    
                    // 从链接中提取日期 /fantasy-5/numbers/MM-DD-YYYY
                    const hrefMatch = href.match(/numbers\/(\d{2})-(\d{2})-(\d{4})/);
                    if (hrefMatch) {
                        const month = parseInt(hrefMatch[1]);
                        const day = parseInt(hrefMatch[2]);
                        const yr = parseInt(hrefMatch[3]);
                        const dateStr = `${yr}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
                        
                        // 从相邻元素提取号码
                        const parent = el.closest('tr, li, div, section') || el.parentElement;
                        if (parent) {
                            const parentText = parent.innerText;
                            const nums = [];
                            const numRegex = /\b(\d{1,2})\b/g;
                            let match;
                            while ((match = numRegex.exec(parentText)) !== null) {
                                const n = parseInt(match[1]);
                                if (n >= 1 && n <= 39 && nums.length < 5) {
                                    // 排除日期中的数字
                                    if (n !== month && n !== day) {
                                        nums.push(n);
                                    }
                                }
                            }
                            
                            if (nums.length === 5) {
                                results.push({ date: dateStr, numbers: nums });
                            }
                        }
                    }
                });
                
                return results;
            });
            
            // 合并两种提取结果，去重
            const dateSet = new Set(draws.map(d => d.date));
            for (const d of domDraws) {
                if (!dateSet.has(d.date)) {
                    draws.push(d);
                    dateSet.add(d.date);
                }
            }
        }
        
        console.log(`  ${year}: ${draws.length} 条`);
        return draws;
        
    } catch (e) {
        console.log(`  ${year} 失败: ${e.message}`);
        return [];
    } finally {
        await page.close();
    }
}


async function main() {
    const args = process.argv.slice(2);
    let years = [];
    
    for (let i = 0; i < args.length; i++) {
        if (args[i] === '--year' && args[i+1]) {
            years.push(parseInt(args[i+1]));
            i++;
        }
    }
    
    if (years.length === 0) {
        years = [2022, 2023, 2024, 2025];
    }
    
    console.log('╔══════════════════════════════════════╗');
    console.log('║  Puppeteer v2: Fantasy 5 数据抓取   ║');
    console.log('║  年份: ' + years.join(', ') + '                   ║');
    console.log('╚══════════════════════════════════════╝');
    
    if (!fs.existsSync(OUTPUT_DIR)) {
        fs.mkdirSync(OUTPUT_DIR, { recursive: true });
    }
    
    const browser = await puppeteer.launch({
        headless: true,
        executablePath: CHROME_PATH,
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
    });
    
    let allDraws = [];
    
    for (const year of years) {
        console.log(`\n── ${year} ──`);
        const draws = await scrapeYear(browser, year);
        
        // 转换为标准格式
        const formatted = draws.map(d => ({
            draw_date: d.date,
            num1: String(d.numbers[0]),
            num2: String(d.numbers[1]),
            num3: String(d.numbers[2]),
            num4: String(d.numbers[3]),
            num5: String(d.numbers[4]),
            jackpot_amount: '0'
        }));
        
        allDraws.push(...formatted);
        
        const yearPath = path.join(OUTPUT_DIR, `fantasy5_${year}.json`);
        fs.writeFileSync(yearPath, JSON.stringify(formatted, null, 2));
        console.log(`  → ${yearPath} (${formatted.length}条)`);
    }
    
    await browser.close();
    
    // 去重+排序
    const dateSet = new Set();
    const uniqueDraws = [];
    for (const d of allDraws) {
        if (!dateSet.has(d.draw_date)) {
            dateSet.add(d.draw_date);
            uniqueDraws.push(d);
        }
    }
    uniqueDraws.sort((a, b) => a.draw_date.localeCompare(b.draw_date));
    
    const outputPath = path.join(OUTPUT_DIR, 'fantasy5_all_scraped.json');
    fs.writeFileSync(outputPath, JSON.stringify(uniqueDraws, null, 2));
    
    console.log('\n╔══════════════════════════════════════╗');
    console.log(`║  完成! 总计: ${uniqueDraws.length} 条            ║`);
    if (uniqueDraws.length > 0) {
        console.log(`║  范围: ${uniqueDraws[0].draw_date} ~ ${uniqueDraws[uniqueDraws.length-1].draw_date}  ║`);
    }
    console.log(`║  输出: ${outputPath}               ║`);
    console.log('╚══════════════════════════════════════╝');
    console.log('\n合并数据: python data/merge_scraped_data.py');
}


main().catch(e => {
    console.error('失败:', e);
    process.exit(1);
});
