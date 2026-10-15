FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd -m -u 10001 ft
COPY --chown=ft:ft manage.py serve.py backup.py ./
COPY --chown=ft:ft ft ./ft
COPY --chown=ft:ft core ./core
COPY --chown=ft:ft templates ./templates
COPY --chown=ft:ft static ./static
RUN mkdir -p /data && chown ft:ft /data
USER ft
ENV FT_DATA_DIR=/data FT_HOST=0.0.0.0 FT_PORT=4180 PYTHONUNBUFFERED=1
EXPOSE 4180
CMD ["sh", "-c", "python manage.py migrate --noinput && python serve.py"]
