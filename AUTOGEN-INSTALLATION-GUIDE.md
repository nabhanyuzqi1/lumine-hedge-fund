# Microsoft AutoGen Integration Guide for Lumine Hedge Fund

## Installation Complete ✅

**Date:** August 13, 2026  
**Status:** READY FOR USE  

---

## What Was Installed

### Package Information
- **Package:** `pyautogen` (Microsoft AutoGen)
- **Version:** 0.3.3
- **Installation Method:** pip
- **Location:** backend/src/lumine/autogen_pipeline/orchestration.py

---

## Usage Example

```python
from lumine.autogen_pipeline.orchestration import (
    AutoGenOrchestrator, 
    AutoGenConfig, 
    AgentSpec
)

async def example_usage(session):
    # Initialize orchestrator
    config = AutoGenConfig(model_name="gpt-5.5")
    orchestrator = AutoGenOrchestrator(config)
    
    # Register analysts
    tech_agent = await orchestrator.register_agent(AgentSpec(
        name="technical_analyst",
        role="Technical Analyst",
        description="Analyzes charts and indicators",
        system_message="You are a technical analyst.",
        llm_config={"model": "gpt-5.5"},
    ))
    
    macro_agent = await orchestrator.register_agent(AgentSpec(
        name="macro_analyst",
        role="Macro Analyst",
        description="Analyzes economic data",
        system_message="You are a macroeconomic analyst.",
        llm_config={"model": "gpt-5.5"},
    ))
    
    # Create group chat
    group_chat = orchestrator.create_group_chat([tech_agent, macro_agent])
    
    # Run debate
    result = await orchestrator.run_conversation(
        session=session,
        starter_message="Analyze XAUUSD market conditions.",
        workflow_id="xauu_analysis_001",
        lineage_id="lineage_001",
    )
    
    print(f"Conversation: {result['turns']} turns")
```

---

## Key Features

✅ Deterministic agent orchestration  
✅ Schema validation on all outputs  
✅ Full audit trail in database  
✅ Budget controls per conversation  
✅ Checkpoint/replay capability  

---

## Next Steps

1. Run unit tests: `pytest backend/tests/unit/test_autogen_orchestration.py -v`
2. Integrate into investment committee workflow
3. Monitor LLM costs during development
4. Add integration tests for end-to-end flow

---

*Ready to use!*  
*Last Updated: August 13, 2026*
