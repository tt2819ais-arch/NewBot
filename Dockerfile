FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Создаем папку для медиа файлов
RUN mkdir -p media

CMD ["python", "-m", "bot.main"]
