# 贡献指南

感谢你对 TextSQL-Agent 的关注！欢迎提交 Issue 和 Pull Request。

## 开发环境搭建

1. Fork 本仓库
2. 克隆到本地：
   ```bash
   git clone https://github.com/你的用户名/TextSQL-Agent.git
   cd TextSQL-Agent
   ```
3. 创建虚拟环境并安装依赖：
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. 复制环境变量配置：
   ```bash
   cp .env.example .env
   ```

## 提交规范

### 代码规范
- 遵循 PEP 8 Python 编码规范
- 使用 4 空格缩进
- 函数和类需要添加 docstring 注释
- 新增功能需配套单元测试

### Commit 规范
采用 Conventional Commits 格式：
```
<type>(<scope>): <subject>

<description>
```

type 类型：
- `feat`: 新功能
- `fix`: 修复 bug
- `docs`: 文档更新
- `style`: 代码格式调整
- `refactor`: 重构
- `test`: 测试相关
- `chore`: 构建/工具链相关

### Pull Request 流程
1. 从 main 分支创建新分支：`git checkout -b feature/你的功能名`
2. 完成开发并提交代码
3. 确保所有测试通过：`python main.py --test`
4. 提交 PR，详细描述改动内容和原因

## 报告 Issue

提交 Bug 时请包含：
- 操作系统与 Python 版本
- 复现步骤
- 错误日志与截图
- 期望行为

## 功能建议

欢迎通过 Issue 提出新功能建议，描述清楚使用场景和期望效果。
