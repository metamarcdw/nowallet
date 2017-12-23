clean:
	rm -rf __pycache__/ .cache/ .mypy_cache/
	rm -f lint.txt type.txt nowallet.log nowallet.ini
	rm -rf nowallet/__pycache__/ nowallet/.mypy_cache/

init:
	pip3 install -r requirements.txt

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

lint:
	pylint nowallet/*.py > lint.txt

type:
	mypy --ignore-missing-imports nowallet/*.py > type.txt

.PHONY: clean init install uninstall test go go-spend go-kivy lint type
