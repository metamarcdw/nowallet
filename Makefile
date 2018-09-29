clean:
	rm -rf __pycache__/ .cache/ .mypy_cache/
	rm -f lint.txt type.txt nowallet.log nowallet.ini
	rm -rf nowallet/__pycache__/ nowallet/.mypy_cache/

init:
	pip3 install -r requirements.txt

init-kivy:
	pip3 install -r requirements-kivy.txt

init-dev:
	pip3 install -r requirements-dev.txt

install:
	pip3 install -e .

uninstall:
	pip3 uninstall nowallet

test:
	tox

go:
	python3 -m nowallet

go-spend:
	python3 -m nowallet spend rbf

go-kivy:
	python3 main.py

go-daemon:
	export NW_LOG=ERR && python3 nowalletd.py foo1 bar1

go-server:
	python3 server.py tbtc

go-gunicorn:
	gunicorn server:global_app --bind unix:endpoint.sock --worker-class aiohttp.GunicornWebWorker &

lint:
	pylint nowallet/*.py > lint.txt

type:
	mypy --ignore-missing-imports nowallet/*.py > type.txt

.PHONY: clean init init-kivy init-dev install uninstall test go go-spend go-kivy go-daemon go-server go-gunicorn lint type
