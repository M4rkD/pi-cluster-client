from PySide2.QtCore import *
import numpy as np
from fabric import Connection
import os

cluster_address = "pi@10.0.0.253"
cluster_path = "Documents/picluster"
local_path = os.environ['PWD']
nmeasurements = 20
cluster = Connection(cluster_address)


def get_cfd_output(index):
    ''' Get the current stdout of the ongoing run
        or the previous run.
    '''
    directory = '{}/outbox/run{}'.format(cluster_path, index)
    with cluster.cd(directory):
        return cluster.run('cat output', hide=True).stdout


def get_run_completion_percentage(index):
    ''' Read the completion percentage of the run
    '''
    output = get_cfd_output(index)

    found = False
    try:
        for line in output.split("\n"):
            if "MAIN:  Time:" in line:
                timestring = line.split(' ')[3]
            numbers = timestring.split('/')
            percentage = float(numbers[0]) / float(numbers[1])
        else:
            percentage = 0
    except:
        percentage = 0
    return percentage


def queue_run(contour, index):
    # save contour to file and copy to the cluster inbox
    filename = "contour.dat"
    write_outline(filename, contour)

    # copy the contour
    remote_name = '{}/contour.dat'.format(cluster_path)
    cluster.put(filename, remote=remote_name)

    # copy a signal file accross
    remote_name = '{}/inbox/run{}'.format(cluster_path, index)
    cluster.put(filename, remote=remote_name)


class RunCompleteWatcher(QFileSystemWatcher):
    ''' Periodically polls the cluster to check for finished jobs
        Gets the resulting images as numpy arrays and 
        communicates them through a signal
    '''

    completed = Signal(int)

    def __init__(self, parent=None):
        self.existing_runs = set(os.listdir("{}/outbox/signal/".format(local_path)))

        path = "{}/outbox/signal/".format(local_path)
        filepath = "{}/signal_file".format(path)
        super().__init__([path, filepath], parent)

        self.directoryChanged.connect(self.run_complete)

    def run_complete(path):
        runs = set(os.listdir(path))

        new_run = runs - self.existing_runs

        for run in new_runs:
            index = run.replace("run", '')
            index = int(index)
            print("Run {} is complete!".format(index))
            existing_runs.add(run)
            completed(index)



def test_submit():
    contour = np.loadtxt("scf1540984574-outline-coords.dat")
    queue_run(contour, 2)
    while True:
        print(get_run_completion_percentage(2))
        time.sleep(1)


def test_app():
    app = QApplication(sys.argv)
    label = QLabel("<font color=red size=40>Hello World!</font>")
    label.show()
    rcw = RunCompleteWatcher()
    sys.exit(app.exec_())


#test_submit()
#test_app()

