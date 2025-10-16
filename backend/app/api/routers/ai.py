from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError
from transformers import pipeline

from app.schemas.simulation import SimulationOut

router = APIRouter(prefix="/ai", tags=["AI"])

summarizer = pipeline("summarization", model="facebook/bart-large-cnn")


@router.post("/analyze-simulations")
def analyze_simulations(payload: List[SimulationOut]):
    """
    Analyze a list of simulations and return a summary of their metadata.

    FIXME: This route causes FastAPI to register an extra SimulationOut schema
    on the OpenAPI docs, which is not ideal.
    """
    try:
        sim_descriptions = [_describe_sim(sim) for sim in payload]

        if len(sim_descriptions) <= 5:
            input_text = (
                "Compare the following E3SM simulation metadata. "
                "Summarize key similarities and differences in tag, campaign, compset, resolution, machine, and notes.\n\n"
                + "\n".join(sim_descriptions)
                + "\n\nSummary:"
            )
            result = summarizer(
                input_text, max_length=300, min_length=100, do_sample=False
            )

            return {"summary": result[0]["summary_text"]}
        else:
            final_summary = _summarize_chunks(sim_descriptions)

            return {"summary": final_summary}
    except ValidationError as ve:
        raise HTTPException(
            status_code=422, detail=f"Validation error: {ve.errors()}"
        ) from ve
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Summarization failed: {str(e)}"
        ) from e


def _describe_sim(sim: SimulationOut) -> str:
    """
    Generate a string description of a simulation using its metadata.
    """
    return (
        f"Name: {sim.name}, Case Name: {sim.case_name}: "
        f"Tag: {sim.git_tag}, Campaign: {sim.campaign_id}, Compset: {sim.compset}, "
        f"Resolution: {sim.grid_resolution}, Machine: {sim.machine_id}, Notes: {sim.notes_markdown or 'n/a'}"
    )


def _summarize_chunks(simulations: List[str], chunk_size: int = 4) -> str:
    """
    Summarize a list of simulation descriptions in chunks.
    """
    chunks = [
        simulations[i : i + chunk_size] for i in range(0, len(simulations), chunk_size)
    ]
    intermediate = []

    for chunk in chunks:
        input_text = (
            "Compare the following E3SM simulation metadata. "
            "Summarize key similarities and differences in tag, campaign, compset, resolution, machine, and notes.\n\n"
            + "\n".join(chunk)
            + "\n\nSummary:"
        )
        res = summarizer(input_text, max_length=250, min_length=80, do_sample=False)
        intermediate.append(res[0]["summary_text"])

    final_input = (
        "Given these summaries of E3SM simulation metadata groups, synthesize overall trends, differences, and recurring patterns in tag, campaign, compset, resolution, machine, and notes.\n\n"
        + "\n".join(intermediate)
        + "\n\nOverall Summary:"
    )
    result = summarizer(final_input, max_length=300, min_length=100, do_sample=False)
    return result[0]["summary_text"]
