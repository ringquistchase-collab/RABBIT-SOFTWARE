from fastapi import APIRouter, HTTPException
from core.models import AgentRequest, AgentResponse
from agents.dev_agent import DevAgent
from agents.security_agent import SecurityAgent
from agents.research_agent import ResearchAgent

router = APIRouter()

_REGISTRY = {
    "dev":      DevAgent(),
    "security": SecurityAgent(),
    "research": ResearchAgent(),
}


@router.post("/", response_model=AgentResponse)
async def run_agent(req: AgentRequest):
    agent = _REGISTRY.get(req.agent)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {req.agent}")
    try:
        output = await agent.run(req.command, req.params)
        return AgentResponse(agent=req.agent, output=output)
    except Exception as exc:
        return AgentResponse(agent=req.agent, output=None, ok=False, error=str(exc))


@router.get("/")
async def list_agents():
    return {"agents": list(_REGISTRY.keys())}
