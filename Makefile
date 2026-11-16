.PHONY: run fault console eval test demo clean

run:
	python -m harness.cli run

fault:
	python -m harness.cli run --fault

console:
	python -m harness.console --port 8080

eval:
	python -m eval.run_eval

test:
	python -m unittest discover -s tests -v

demo:
	python -m harness.cli run
	python -m harness.cli run --fault
	python -m eval.run_eval

clean:
	rm -f runs.db eval/eval_runs.db eval/results.md eval/results.json
	find . -name __pycache__ -type d -exec rm -rf {} +
