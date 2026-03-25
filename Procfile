# Procfile — usado por Heroku e Railway (modo Procfile)
# O $PORT é injetado automaticamente pelo runtime
web: uvicorn backend:app --host 0.0.0.0 --port $PORT --timeout-keep-alive 300 --log-level info
