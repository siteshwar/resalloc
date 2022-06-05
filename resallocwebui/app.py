import os
from flask import Flask, render_template
from resallocserver.app import session_scope
from resallocserver.app import app as application
from resallocserver.logic import QResources
from resalloc.helpers import load_config_file, RState
from resallocserver import models
from resallocwebui import static_folder

tmpl_dir = os.path.join(static_folder, "templates")
app = Flask(__name__, template_folder=tmpl_dir)
app.static_folder = os.path.join(static_folder, "static")


@app.route("/")
def home():
    return "OK"


@app.route('/resources')
def resources():
    with session_scope() as session:
        resources = session.query(models.Resource)
    config = application.instantiate_config()
    pools = load_config_file(os.path.join(config["config_dir"], "pools.yaml"))
    resources_list = append_resources(resources)
    resources_status = {}
    status = {"UP": 0, "STARTING": 0, "DELETING": 0, "RELEASING": 0, "ENDED": 0, "TAKEN": 0}
    for resource in resources_list:
        resources_status.setdefault(resource["pool"], status)
        resources_status[resource["pool"]][resource["status"]] += 1
        if resource["ticket"]:
            resources_status[resource["pool"]]["TAKEN"] += 1
    information = {}
    for name, status in resources_status.items():
        information[name] = {
            "available": pools[name]["max"] - status["TAKEN"],
            "max": pools[name]["max"],
            "status": status,
        }
    return render_template('resources.html', information=information)


@app.route("/pools")
def pools():
    # We want to count resources in all states except for ENDED because that
    # could cause performance issues on a large database. Also, resources that
    # are UP can be distinguished between READY and TAKEN.
    columns = RState.values.copy()
    columns.remove(RState.ENDED)
    columns.extend(["READY", "TAKEN"])

    # This will be a two-dimensional array,
    # e.g. result["copr_hv_x86_64_01_prod"]["STARTING"]
    result = {}

    with session_scope() as session:
        # Prepare the two-dimensional array, and fill it with zeros
        for pool in session.query(models.Pool):
            result[pool.name] = dict.fromkeys(columns, 0)

        # Iterate over running resources and calculate how many is starting,
        # deleting, etc.
        qresources = QResources(session=session)
        for resource in qresources.on():
            result[resource.pool][resource.state] += 1

            if resource.state != RState.UP:
                continue
            key = "TAKEN" if resource.taken else "READY"
            result[resource.pool][key] += 1

    return render_template("pools.html", information=result)


def append_resources(resources):
    resources_list = []
    for resource in resources.all():
        resources_list.append({
            'id': resource.id,
            'name': resource.name,
            'pool': resource.pool,
            'tags': ', '.join(list(resource.tag_set)),
            'status': resource.state,
            'releases': resource.releases_counter,
            'ticket': resource.ticket.id if resource.ticket else None,
        })
    return resources_list


if __name__ == '__main__':
    app.run(host="0.0.0.0")
