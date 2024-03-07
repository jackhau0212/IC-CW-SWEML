# Team Kronprinzen AKI Detection System v 1.0 

This repo represents the final deployed version of our AKI Detection system. 

The system is able to receive live messages from a hospital server, tracking patient admissions and blood test results. It will notify the hospital pager
system immedieatly if an AKI event is detected. 

## Directory Structure

```
# Deployed Files:

├── model.py # AKI Detection Inference System
├── trained_model.pkl # RandomForest model trained to detect AKI events
├── Dockerfile # Docker build
├── coursework4.yaml # YAML file for Kubernetes deployment
├── backup.txt # Missed PAS events (from our declared incident)
├── hospital-history 
│   ├── history.csv # Patient data prior to system deployment
├── requirements.txt # Pkg requirements for deployment

# Other files:

├── unit_tests.py # Unit tests for validating message processing 
├── simulator.py # simulator to test hopsital environment
├── simulator_test.py # test for the simulator 
├── aki.csv # Expected AKI events for simulator
├── database.pkl # Database generated from simulator

# Documentation:

├── docs
│    ├── design_document.pdf # System design
│    ├── post_mortem.pdf # Examination of our incident

```

## System Overview 

This is a **brief** overview of how our system works. Please see the attached `design_document.pdf` for a more detailed rundown of the system. 

- `model.py` is the implementation of our inference system, it processes incoming messages from the hopsital and uses the data to inference with `trained_model.pkl` - a trained RandomForest implementation.
- On startup, the system will first check for a `database.pkl` file in the `state` folder (see Kubernetes directory structure in `design_document.pdf`). This would consist of the most up-to-date version of the database in the event the system either crashed or was shutdown.
- If `database.pkl` does not exist (e.g. on the when the system is first run) then data will instead be loaded from `hospital-history/history.csv`.
- The system will continuously monitor the connection socket with the hospital servers and automatically process data and alert the pager system if any AKI events occur.
- The current database state `database.pkl` is updated every new message received.
- If a disconnection occurs on either end, the system will make up to 100 attempts over ~5 minutes to restablish connection. 

*Note*: We experienced an incident (see `post_mortem.pdf`) where we lost our peristant state. Therefore, our current deployment also reads from `backup.txt` which contains all the hopsital admissions up to our incident. The incident has been fixed and this would not be necessary in future deployments.
