from pydantic import BaseModel, ConfigDict, Field


# - Defines the one JSON contract shared by all provisioning queue producers and consumers.
# - Architectural Purpose: Prevents queue payload keys from drifting between webhook, recovery, and worker code.
# - Plain-English: 'Agree on the exact message shape before one component sends it to another.'
class ProvisioningMessage(BaseModel):
    # - Rejects unknown fields so obsolete or misspelled payload formats fail at the boundary.
    model_config = ConfigDict(extra="forbid")

    # - Requires the positive database identifier used by the worker to claim a student row.
    id: int = Field(gt=0)


# - Serializes an identifier with the canonical queue schema.
# - Architectural Purpose: Gives scripts and API code one reliable message-building path.
# - Plain-English: 'Wrap a student ID in the queue format the worker expects.'
def serialize_provisioning_message(student_id: int) -> str:
    return ProvisioningMessage(id=student_id).model_dump_json()


# - Parses queue text using the same schema producers use for serialization.
# - Architectural Purpose: Makes invalid or incompatible messages explicit before database work begins.
# - Plain-English: 'Check that a queue message has the expected student ID.'
def parse_provisioning_message(message_body: str) -> ProvisioningMessage:
    return ProvisioningMessage.model_validate_json(message_body)
