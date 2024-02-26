FROM ubuntu:jammy
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get -yq install python3-pip
COPY simulator.py /simulator/
COPY simulator_test.py /simulator/
WORKDIR /simulator
RUN ./simulator_test.py
COPY requirements.txt /simulator/
RUN pip3 install -r /simulator/requirements.txt
COPY messages.mllp /simulator/
COPY trained_model.pkl /simulator/
# COPY history.csv /simulator/
COPY model.py /simulator/
COPY backup.txt /simulator/
# ENV MLLP_ADDRESS=host.docker.internal:8440
# ENV PAGER_ADDRESS=host.docker.internal:8441
EXPOSE 8440
EXPOSE 8441
CMD /simulator/model.py --model=/simulator/trained_model.pkl