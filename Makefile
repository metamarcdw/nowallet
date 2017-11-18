init:
	pip install -r requirements.txt

install:
	pip install -e .

uninstall:
	pip uninstall nowallet

test:
	pytest

go:
	python3 nowallet/nowallet.py

go-kivy:
	python3 kivy_ui/main.py

.PHONY: init install uninstall test go go-kivy
