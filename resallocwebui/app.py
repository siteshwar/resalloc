import os
from flask import Flask, render_template
from resallocserver.app import session_scope
from resallocserver.logic import QResources
from resallocserver.manager import reload_config
from resalloc.helpers import RState
from resallocwebui import staticdir, templatedir


app = Flask(__name__, template_folder=templatedir)
app.static_folder = staticdir


@app.route("/")
def home():
    return render_template("home.html", resources=resources)


@app.route('/resources')
def resources():
    with session_scope() as session:
        qresources = QResources(session=session)
        resources = qresources.on()
        return render_template("resources.html", resources=resources)


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

    # Read configuration from pools.yaml
    pools_config = reload_config()

    # Prepare the two-dimensional array, and fill it with zeros
    for name, pool in pools_config.items():
        result[name] = dict.fromkeys(columns, 0)
        result[name]["MAX"] = pools_config[name].max

    with session_scope() as session:
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


if __name__ == '__main__':
    app.run(host="0.0.0.0")
