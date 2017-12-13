clean:
	rm -rf __pycache__/ .cache/ .mypy_cache/
	rm -f lint.txt type.txt nowallet.log
	rm -rf nowallet/__pycache__/ nowallet/.mypy_cache/

init:
	pip3 install -r requirements.txt

install:
	pip3 install -e .

uninstall:
	pip3 uninstall nowallet

test:
	pytest

go:
	python3 nowallet/nowallet.py

go-kivy:
	python3 kivy_ui/main.py

lint:
	pylint nowallet/*.py > lint.txt

type:
	mypy --ignore-missing-imports nowallet/*.py > type.txt

.PHONY: clean init install uninstall test go go-kivy lint type
