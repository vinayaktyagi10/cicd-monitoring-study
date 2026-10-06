PY      := .venv/bin/python
SCRIPTS := experiments/scripts
CAMPAIGN ?= $(lastword $(sort $(wildcard experiments/replication/*)))

.PHONY: help venv test tables stats validate figures verify-figures paper reproduce \
        image campaign campaign-cicd validate-campaign overhead grafana-figure

help:
	@echo "No Docker needed (derive everything from raw data):"
	@echo "  make reproduce          venv + test + tables + stats + validate + figures + verify + paper"
	@echo "Docker needed (collect new data):"
	@echo "  make image              build the subject app image"
	@echo "  make campaign           replication campaign, all experiments except CI/CD (~3h)"
	@echo "  make campaign-cicd      same plus 8 real GitHub Actions runs"
	@echo "  make validate-campaign  original vs replication, overhead analysis [CAMPAIGN=dir]"
	@echo "  make grafana-figure     recapture Fig. 3"

venv: .venv/.installed
.venv/.installed: experiments/requirements.txt app/requirements.txt
	python3 -m venv .venv
	$(PY) -m pip install -q -r experiments/requirements.txt -r app/requirements.txt
	touch $@

test: venv
	$(PY) -m pytest -q experiments/tests app/test_main.py

tables: venv
	$(PY) $(SCRIPTS)/aggregate.py
	git diff --exit-code --stat experiments/results/ && echo "results/ identical to committed tables"
	cd $(SCRIPTS) && ../../$(PY) paper_tables.py

stats: venv
	$(PY) $(SCRIPTS)/statistical_analysis.py

validate: venv
	cd $(SCRIPTS) && ../../$(PY) validate.py

figures: venv
	$(PY) paper/figures/generate_figures.py

verify-figures: venv
	$(PY) paper/figures/verify_figures.py

paper:
	cd paper && latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=build paper.tex >/dev/null \
	  && cp build/paper.pdf paper.pdf && echo "built paper/paper.pdf"

reproduce: test tables stats validate verify-figures paper

image:
	docker compose build app

campaign: venv
	$(PY) $(SCRIPTS)/campaign.py

campaign-cicd: venv
	$(PY) $(SCRIPTS)/campaign.py --with-cicd

validate-campaign: venv
	cd $(SCRIPTS) && ../../$(PY) validate.py --campaign ../../$(CAMPAIGN)
	$(PY) $(SCRIPTS)/analyze_overhead.py $(CAMPAIGN)/raw/exp6_overhead.csv
	@if [ -f $(CAMPAIGN)/raw/exp6_overhead_loadgen4.csv ]; then \
	  $(PY) $(SCRIPTS)/analyze_overhead.py $(CAMPAIGN)/raw/exp6_overhead_loadgen4.csv \
	    --outdir $(CAMPAIGN)/results/overhead_loadgen4; fi

grafana-figure: venv
	$(PY) paper/figures/capture_grafana.py
