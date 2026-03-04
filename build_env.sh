#!/bin/bash

# 颜色定义 | Color Definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息 | Print colored messages
print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[i]${NC} $1"
}

# 打印标题 | Print Title
echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║    Travel Assistant 项目依赖安装脚本 | uv 环境初始化版         ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# ==========================================
# 步骤 1: 检测操作系统
# Step 1: Detect OS
# ==========================================
print_info "[1/4] 检测操作系统... | Detecting OS..."

if [[ "$OSTYPE" == "darwin"* ]]; then
    print_success "检测到 MacOS 系统 | MacOS detected"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    print_success "检测到 Linux 系统 | Linux detected"
else
    print_error "未知的操作系统，可能表现异常 | Unknown OS: $OSTYPE"
fi
echo ""

# ==========================================
# 步骤 2: 检查 uv 是否安装
# Step 2: Check uv
# ==========================================
echo "[2/4] 检查 uv 环境... | Checking uv environment..."

if ! command -v uv &> /dev/null; then
    print_error "未检测到 uv 包管理器！| uv not detected!"
    echo "请先使用以下命令安装 uv："
    echo "curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "或使用 pip: pip install uv"
    exit 1
else
    print_success "检测到 uv: $(uv --version)"
fi
echo ""

# ==========================================
# 步骤 3: 检查并创建虚拟环境
# Step 3: Check/create virtulenv
# ==========================================
echo "[3/4] 准备虚拟环境... | Preparing virtualenv..."

if [ ! -d ".venv" ]; then
    print_info "正在创建虚拟环境... | Creating .venv..."
    uv venv .venv
    
    if [ $? -eq 0 ]; then
        print_success "虚拟环境创建成功 | virtualenv created successfully"
    else
        print_error "虚拟环境创建失败 | Failed to create virtualenv"
        exit 1
    fi
else
    print_info "虚拟环境已存在 | .venv already exists"
fi

# 激活环境供脚本后续使用
source .venv/bin/activate
print_success "虚拟环境已激活 | virtualenv activated"
echo ""

# ==========================================
# 步骤 4: 安装 Python 依赖
# Step 4: Install Python dependencies
# ==========================================
echo "[4/4] 安装 Python 依赖... | Installing Python dependencies..."

if [ ! -f "requirements.txt" ]; then
    print_error "未找到 requirements.txt | requirements.txt not found"
    exit 1
fi

print_info "使用 uv 快速安装依赖包... | Installing packages with uv..."
echo ""

uv pip install -r requirements.txt

if [ $? -ne 0 ]; then
    print_error "依赖安装失败 | Dependency installation failed"
    exit 1
fi

print_success "依赖安装完成 | Dependencies installed successfully"
echo ""

# ==========================================
# 安装完成 | Installation Complete
# ==========================================
echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║          安装成功！| Installation Successful!                  ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

print_info "执行信息 | Environment Info:"
echo "  Python: $(python --version 2>&1)"
echo "  路径 | Path: $(which python)"
echo ""

print_success "现在可以运行项目了！请先复制配置文件后启动服务："
echo -e "${YELLOW}1. 激活环境 (每次新开终端需执行):${NC}"
echo "   source .venv/bin/activate"
echo -e "${YELLOW}2. 准备配置文件:${NC}"
echo "   cp config.toml.example config.toml"
echo -e "${YELLOW}3. 运行服务:${NC}"
echo "   uv run uvicorn agent_fastapi:app --host 0.0.0.1 --port 8000"
echo "   或 CLI 模式: uv run python cli.py"