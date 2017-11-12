init:
	pip install -r requirements.txt

install:
	pip install -e .

uninstall:
	pip uninstall nowallet

test:
	pytest

go:
	python nowallet/nowallet.py

.PHONY: init install uninstall test go
