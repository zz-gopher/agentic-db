FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

# 复制依赖文件并利用清华源加速安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制代码到容器内
COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]