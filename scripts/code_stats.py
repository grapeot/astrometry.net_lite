#!/usr/bin/env python3
"""
统计代码库代码行数（排除net文件夹）
"""
import os
from pathlib import Path
from collections import defaultdict
import json
from datetime import datetime

# 文件类型映射
FILE_TYPES = {
    '.py': 'Python',
    '.ts': 'TypeScript',
    '.tsx': 'TypeScript React',
    '.js': 'JavaScript',
    '.jsx': 'JavaScript React',
    '.html': 'HTML',
    '.css': 'CSS',
    '.md': 'Markdown',
    '.json': 'JSON',
    '.sh': 'Shell',
    '.toml': 'TOML',
    '.yaml': 'YAML',
    '.yml': 'YAML',
    '.dockerfile': 'Docker',
    '.gitignore': 'Config',
    '.env': 'Config',
    '.example': 'Config',
    '.development': 'Config',
    '.dockerignore': 'Config',
}

def count_lines(file_path):
    """统计文件行数"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return len(f.readlines())
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return 0

def get_file_type(file_path):
    """获取文件类型"""
    path = Path(file_path)
    name = path.name.lower()
    
    # 检查特殊文件名（无扩展名或特殊扩展名）
    if name == 'dockerfile':
        return 'Docker'
    if name == '.gitignore' or name.endswith('.gitignore'):
        return 'Config'
    if name.startswith('.env'):
        return 'Config'
    if name == '.dockerignore':
        return 'Config'
    
    ext = path.suffix.lower()
    return FILE_TYPES.get(ext, 'Other')

def should_exclude(path):
    """判断是否应该排除"""
    path_str = str(path)
    parts = Path(path).parts
    
    # 排除net文件夹
    if 'net' in parts:
        return True
    
    # 排除常见的非代码目录（检查路径的任意部分）
    exclude_dirs = ['node_modules', '__pycache__', '.git', 'venv', 'mongodb_data', 
                    'data', 'logs', 'astrometry_indexes', '.pytest_cache', '.mypy_cache']
    
    for exclude_dir in exclude_dirs:
        if exclude_dir in parts:
            return True
    
    # 排除特定文件类型（数据文件、日志等）
    ext = Path(path).suffix.lower()
    exclude_exts = ['.fits', '.log', '.pid', '.csv', '.svg', '.png', '.jpg', '.jpeg', '.gif']
    if ext in exclude_exts:
        return True
    
    # 排除没有扩展名的数据文件（mongodb日志等）
    if not ext and any(x in path_str for x in ['mongodb_data', 'diagnostic.data', 'journal']):
        return True
    
    return False

def scan_directory(root_dir):
    """扫描目录并统计代码"""
    stats = defaultdict(lambda: {'files': 0, 'lines': 0, 'files_list': []})
    
    root_path = Path(root_dir)
    
    for file_path in root_path.rglob('*'):
        if file_path.is_file() and not should_exclude(file_path):
            file_type = get_file_type(file_path)
            lines = count_lines(file_path)
            
            stats[file_type]['files'] += 1
            stats[file_type]['lines'] += lines
            stats[file_type]['files_list'].append({
                'path': str(file_path.relative_to(root_path)),
                'lines': lines
            })
    
    return dict(stats)

def generate_html(stats, output_path):
    """生成HTML可视化"""
    # 准备数据
    types = list(stats.keys())
    files_data = [stats[t]['files'] for t in types]
    lines_data = [stats[t]['lines'] for t in types]
    
    # 计算总计
    total_files = sum(files_data)
    total_lines = sum(lines_data)
    
    # 生成时间戳
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>代码统计可视化</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            padding: 40px;
        }}
        
        h1 {{
            text-align: center;
            color: #333;
            margin-bottom: 10px;
            font-size: 2.5em;
        }}
        
        .subtitle {{
            text-align: center;
            color: #666;
            margin-bottom: 40px;
            font-size: 1.1em;
        }}
        
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }}
        
        .summary-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 25px;
            border-radius: 15px;
            text-align: center;
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.3);
        }}
        
        .summary-card h2 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        
        .summary-card p {{
            font-size: 1.1em;
            opacity: 0.9;
        }}
        
        .charts-container {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
            gap: 30px;
            margin-bottom: 40px;
        }}
        
        .chart-wrapper {{
            background: #f8f9fa;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }}
        
        .chart-wrapper h3 {{
            text-align: center;
            color: #333;
            margin-bottom: 20px;
            font-size: 1.5em;
        }}
        
        .table-container {{
            margin-top: 40px;
            overflow-x: auto;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }}
        
        thead {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}
        
        th, td {{
            padding: 15px;
            text-align: left;
        }}
        
        th {{
            font-weight: 600;
            font-size: 1.1em;
        }}
        
        tbody tr {{
            border-bottom: 1px solid #eee;
        }}
        
        tbody tr:hover {{
            background: #f8f9fa;
        }}
        
        tbody tr:last-child {{
            border-bottom: none;
        }}
        
        .file-count {{
            text-align: center;
            font-weight: 600;
            color: #667eea;
        }}
        
        .lines-count {{
            text-align: center;
            font-weight: 600;
            color: #764ba2;
        }}
        
        .percentage {{
            text-align: center;
            color: #666;
            font-size: 0.9em;
        }}
        
        .footer {{
            text-align: center;
            margin-top: 40px;
            color: #666;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 代码统计报告</h1>
        <p class="subtitle">排除 net 文件夹 | 生成时间: {timestamp}</p>
        
        <div class="summary">
            <div class="summary-card">
                <h2>{total_files}</h2>
                <p>文件总数</p>
            </div>
            <div class="summary-card">
                <h2>{total_lines:,}</h2>
                <p>代码总行数</p>
            </div>
            <div class="summary-card">
                <h2>{len(types)}</h2>
                <p>文件类型</p>
            </div>
        </div>
        
        <div class="charts-container">
            <div class="chart-wrapper">
                <h3>文件数量分布</h3>
                <canvas id="filesChart"></canvas>
            </div>
            <div class="chart-wrapper">
                <h3>代码行数分布</h3>
                <canvas id="linesChart"></canvas>
            </div>
        </div>
        
        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th>文件类型</th>
                        <th class="file-count">文件数</th>
                        <th class="lines-count">代码行数</th>
                        <th class="percentage">文件占比</th>
                        <th class="percentage">行数占比</th>
                    </tr>
                </thead>
                <tbody>
"""
    
    # 按行数排序
    sorted_types = sorted(types, key=lambda t: stats[t]['lines'], reverse=True)
    
    for file_type in sorted_types:
        files = stats[file_type]['files']
        lines = stats[file_type]['lines']
        files_pct = (files / total_files * 100) if total_files > 0 else 0
        lines_pct = (lines / total_lines * 100) if total_lines > 0 else 0
        
        html_content += f"""
                    <tr>
                        <td><strong>{file_type}</strong></td>
                        <td class="file-count">{files}</td>
                        <td class="lines-count">{lines:,}</td>
                        <td class="percentage">{files_pct:.1f}%</td>
                        <td class="percentage">{lines_pct:.1f}%</td>
                    </tr>
"""
    
    html_content += """
                </tbody>
            </table>
        </div>
        
        <div class="footer">
            <p>统计排除: net/ 文件夹及 node_modules, __pycache__, venv, data/jobs 等目录</p>
        </div>
    </div>
    
    <script>
        // 准备数据
        const types = """ + json.dumps(types, ensure_ascii=False) + """;
        const filesData = """ + json.dumps(files_data, ensure_ascii=False) + """;
        const linesData = """ + json.dumps(lines_data, ensure_ascii=False) + """;
        
        // 颜色配置
        const colors = [
            '#667eea', '#764ba2', '#f093fb', '#4facfe', 
            '#43e97b', '#fa709a', '#fee140', '#30cfd0',
            '#a8edea', '#fed6e3', '#ffecd2', '#fcb69f'
        ];
        
        // 文件数量图表
        const filesCtx = document.getElementById('filesChart').getContext('2d');
        new Chart(filesCtx, {{
            type: 'doughnut',
            data: {{
                labels: types,
                datasets: [{{
                    data: filesData,
                    backgroundColor: colors.slice(0, types.length),
                    borderWidth: 2,
                    borderColor: '#fff'
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: true,
                plugins: {{
                    legend: {{
                        position: 'right',
                        labels: {{
                            padding: 15,
                            font: {{
                                size: 12
                            }}
                        }}
                    }},
                    tooltip: {{
                        callbacks: {{
                            label: function(context) {{
                                let label = context.label || '';
                                if (label) {{
                                    label += ': ';
                                }}
                                label += context.parsed + ' 个文件';
                                return label;
                            }}
                        }}
                    }}
                }}
            }}
        }});
        
        // 代码行数图表
        const linesCtx = document.getElementById('linesChart').getContext('2d');
        new Chart(linesCtx, {{
            type: 'bar',
            data: {{
                labels: types,
                datasets: [{{
                    label: '代码行数',
                    data: linesData,
                    backgroundColor: colors.slice(0, types.length).map(c => c + '80'),
                    borderColor: colors.slice(0, types.length),
                    borderWidth: 2
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: true,
                plugins: {{
                    legend: {{
                        display: false
                    }},
                    tooltip: {{
                        callbacks: {{
                            label: function(context) {{
                                return context.parsed.y.toLocaleString() + ' 行';
                            }}
                        }}
                    }}
                }},
                scales: {{
                    y: {{
                        beginAtZero: true,
                        ticks: {{
                            callback: function(value) {{
                                return value.toLocaleString();
                            }}
                        }}
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"HTML报告已生成: {output_path}")

def main():
    root_dir = Path(__file__).parent.parent
    print(f"扫描目录: {root_dir}")
    print("排除文件夹: net/, node_modules, __pycache__, venv, data/jobs, data/uploads, etc.")
    print("正在统计...")
    
    stats = scan_directory(root_dir)
    
    # 打印统计结果
    print("\n=== 代码统计结果 ===")
    total_files = sum(s['files'] for s in stats.values())
    total_lines = sum(s['lines'] for s in stats.values())
    
    print(f"\n总计: {total_files} 个文件, {total_lines:,} 行代码\n")
    
    # 按行数排序显示
    sorted_stats = sorted(stats.items(), key=lambda x: x[1]['lines'], reverse=True)
    
    for file_type, data in sorted_stats:
        print(f"{file_type:20s} {data['files']:4d} 个文件  {data['lines']:8,} 行")
    
    # 生成HTML
    output_path = root_dir / 'code_stats.html'
    generate_html(stats, output_path)
    
    print(f"\n✅ 完成! HTML报告: {output_path}")

if __name__ == '__main__':
    main()

