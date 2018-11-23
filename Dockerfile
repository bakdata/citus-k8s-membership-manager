FROM kennethreitz/pipenv 
COPY . /app
WORKDIR /app

ENTRYPOINT ["python3", "manager.py"]
