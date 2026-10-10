from fastapi import APIRouter, HTTPException, Response

from ..schemas import Run, RunCreate, RunInput, Simulation, SimulationCreate, SimulationPatch, SimulationSummary
from ..store import Store, StoreDep

router = APIRouter(prefix='/simulations', tags=['Simulations'])


@router.get('', response_model=list[SimulationSummary], summary='Simulations, newest first (sidebar list)')
def list_simulations(store: Store = StoreDep):
    return [SimulationSummary(id=s.id, title=s.title, createdAt=s.createdAt, runCount=n) for s, n in store.sims()]


@router.post('', response_model=Simulation, status_code=201, summary='Create an empty simulation. Add its first run with POST /simulations/{id}/runs')
def create_simulation(body: SimulationCreate, store: Store = StoreDep):
    return store.add_sim(body.title)


@router.get('/{sim_id}', response_model=Simulation, summary='A simulation with all its runs')
def get_simulation(sim_id: str, store: Store = StoreDep):
    from ..agent import jobs  # the agent imports the routers' engine code: imported here to keep that one-way
    sim = store.sim(sim_id)
    job = jobs.latest(store, sim_id)
    return {**Simulation.model_validate(sim).model_dump(), 'job': jobs.view(job) if job else None}


@router.patch('/{sim_id}', response_model=Simulation, summary='Rename')
def rename_simulation(sim_id: str, body: SimulationPatch, store: Store = StoreDep):
    return store.rename_sim(store.sim(sim_id), body.title)


@router.delete('/{sim_id}', status_code=204, summary='Delete a simulation and its runs')
def delete_simulation(sim_id: str, store: Store = StoreDep):
    store.delete_sim(store.sim(sim_id))
    return Response(status_code=204)


@router.post('/{sim_id}/duplicate', response_model=Simulation, status_code=201, summary='Copy a simulation with its runs')
def duplicate_simulation(sim_id: str, store: Store = StoreDep):
    return store.duplicate_sim(store.sim(sim_id))


@router.get('/{sim_id}/runs', response_model=list[Run], summary='Version history (v1 first)')
def list_runs(sim_id: str, store: Store = StoreDep):
    return store.sim(sim_id).runs


@router.post('/{sim_id}/runs', response_model=Run, status_code=201, summary='Run the engine and save the result as the next version')
def create_run(sim_id: str, body: RunCreate, store: Store = StoreDep):
    """Runs are append-only.

    `input` holds only the fields to change. On the first run they are applied on top of the default
    run input; afterwards on top of the previous version's input (a what-if, or resolving a flag
    through `resolved`). With `replace: true`, `input` is taken as the complete input instead.
    """
    sim = store.sim(sim_id)
    prev = RunInput.model_validate(sim.runs[-1].input) if sim.runs else None
    input = store.make_input(body.input.model_dump(exclude_unset=True), None if body.replace else prev)
    return store.add_run(sim, input, body.createdBy, body.summary or ('Re-run' if prev else 'Initial run'))


@router.get('/{sim_id}/runs/{version}', response_model=Run)
def get_run(sim_id: str, version: int, store: Store = StoreDep):
    runs = store.sim(sim_id).runs
    if not 1 <= version <= len(runs):
        raise HTTPException(404, f'Simulation {sim_id!r} has no run v{version}')
    return runs[version - 1]
