# API Gateway

## Deployment

Download repository

```bash
git clone https://github.com/Bondifuzz/api-gateway.git
cd api-gateway
```

Build docker image

```bash
docker build -t api-gateway .
```

Run container (locally)

```bash
docker run --net=host --rm -it --name=api-gateway --env-file=.env api-gateway bash
```

## Local development

### Install and run

Using python 3.7+

```bash
git clone https://github.com/Bondifuzz/api-gateway.git && cd api-gateway
pip3 install -r requirements-dev.txt

ln -s local/dotenv .env
ln -s local/docker-compose.yml docker-compose.yml
docker-compose -p api_gateway up -d

python3 -m uvicorn \
    --factory api_gateway.app.main:create_app \
    --host 127.0.0.1 \
    --port 8080 \
    --workers 1 \
    --log-config logging.yaml \
    --lifespan on
```

### Generate API specification

```
python3 -m uvicorn --factory api_gateway.app.main:generate_api_spec
```

### Code documentation

TODO

### Running tests

Install dependencies:

```bash
pip3 install -r requirements-test.txt
```

Running unit tests:

```bash
pytest -vv api-gateway/tests/unit
```

Disable security to run tests

```bash
sed -i "s/COOKIE_MODE_SECURE=.*/COOKIE_MODE_SECURE=0/g" .env
sed -i "s/CSRF_PROTECTION_ENABLED=.*/CSRF_PROTECTION_ENABLED=0/g" .env
pytest -vv api_gateway/tests/integration --ignore=api_gateway/tests/integration/test_csrf_protection.py
```

If you want to run CSRF protection tests, enable security

```bash
sed -i "s/CSRF_PROTECTION_ENABLED=.*/CSRF_PROTECTION_ENABLED=1/g" .env
pytest -vv api_gateway/tests/integration/test_csrf_protection.py
```


### Spell checking

Download cspell and run to check spell in all sources

```bash
sudo apt install nodejs npm
sudo npm install -g cspell
cspell "**/*.{py,md,txt}"
```

### VSCode extensions

- `ms-python.python`
- `ms-python.vscode-pylance`
- `streetsidesoftware.code-spell-checker`
