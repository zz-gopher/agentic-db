FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .

# --- 第 1 步：强制优先安装纯 CPU 版 PyTorch ---
# 必须抢在业务依赖解析之前：sentence-transformers 会依赖 torch，
# 若交由 pip 自行解析，会拉到 PyPI 上捆绑 CUDA 的 torch，额外带入约 5GB 的 nvidia-* / triton。
# 这里用 --index-url 锁定官方 CPU 源，禁止回退到默认源。
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch

# --- 第 2 步：安装剩余业务依赖 ---
# torch 已在第 1 步满足版本约束，pip 不会再次覆盖升级成 CUDA 版
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 项目级审计接口 (/api/v1/audit-project/git) 依赖 git clone 拉取源码
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]