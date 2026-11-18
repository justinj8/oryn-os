import uuid

from oryn.core.db import owner_session
from oryn.models import Workflow, WorkflowVersion
from oryn.workflows.dsl import WorkflowDefinition


async def make_workflow(tenant, definition: dict, enabled: bool = True) -> uuid.UUID:
    d = WorkflowDefinition.model_validate(definition)
    wid, vid = uuid.uuid4(), uuid.uuid4()
    async with owner_session() as s:
        s.add(Workflow(id=wid, tenant_id=tenant.id, name=d.name, trigger_event=d.trigger.event, enabled=enabled))
        await s.flush()
        s.add(
            WorkflowVersion(
                id=vid,
                tenant_id=tenant.id,
                workflow_id=wid,
                version=1,
                definition=d.model_dump(mode="json", by_alias=True),
            )
        )
        await s.flush()
        (await s.get(Workflow, wid)).current_version_id = vid
    return wid
