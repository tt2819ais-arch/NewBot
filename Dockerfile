FROM python:3.11-slim

WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Создаем пустой файл imghdr.py
RUN touch imghdr.py

# Копируем код
COPY . .

# Запускаем бота
CMD ["python", "main.py"]
