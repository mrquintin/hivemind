from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models.simulation_formula import SimulationFormula
from app.schemas.simulation import (
    SimulationFormulaCreate,
    SimulationFormulaOut,
    SimulationFormulaUpdate,
    SimulationRunRequest,
    SimulationRunResponse,
)
from app.services.simulations import run_simulation

router = APIRouter(prefix="/simulations", tags=["simulations"])


@router.get("", response_model=list[SimulationFormulaOut])
def list_formulas(db: Session = Depends(get_db)):
    return db.query(SimulationFormula).all()


@router.post("", response_model=SimulationFormulaOut)
def create_formula(payload: SimulationFormulaCreate, db: Session = Depends(get_db)):
    formula = SimulationFormula(**payload.model_dump())
    db.add(formula)
    db.commit()
    db.refresh(formula)
    return formula


@router.get("/{formula_id}", response_model=SimulationFormulaOut)
def get_formula(formula_id: str, db: Session = Depends(get_db)):
    formula = db.query(SimulationFormula).filter(SimulationFormula.id == formula_id).first()
    if not formula:
        raise HTTPException(status_code=404, detail="Simulation formula not found")
    return formula


@router.put("/{formula_id}", response_model=SimulationFormulaOut)
def update_formula(formula_id: str, payload: SimulationFormulaUpdate, db: Session = Depends(get_db)):
    formula = db.query(SimulationFormula).filter(SimulationFormula.id == formula_id).first()
    if not formula:
        raise HTTPException(status_code=404, detail="Simulation formula not found")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(formula, key, value)
    db.commit()
    db.refresh(formula)
    return formula


@router.delete("/{formula_id}")
def delete_formula(formula_id: str, db: Session = Depends(get_db)):
    formula = db.query(SimulationFormula).filter(SimulationFormula.id == formula_id).first()
    if not formula:
        raise HTTPException(status_code=404, detail="Simulation formula not found")
    db.delete(formula)
    db.commit()
    return {"status": "deleted"}


@router.post("/{formula_id}/run", response_model=SimulationRunResponse)
def run_formula(formula_id: str, payload: SimulationRunRequest, db: Session = Depends(get_db)):
    formula = db.query(SimulationFormula).filter(SimulationFormula.id == formula_id).first()
    if not formula:
        raise HTTPException(status_code=404, detail="Simulation formula not found")
    result = run_simulation(formula, payload.inputs)
    return SimulationRunResponse(outputs=result["outputs"], variables=result["variables"])
