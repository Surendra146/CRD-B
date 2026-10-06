from pydantic import model_validator

from .common import PayloadSchema


class CommunicationRequest(PayloadSchema):
    @model_validator(mode="before")
    @classmethod
    def reject_provider_configuration(cls, data):
        if isinstance(data, dict):
            forbidden = {
                "provider", "graphversion", "phonenumberid", "accesstoken",
                "appsecret", "metaappsecret", "verifytoken",
                "whatsappprovider", "whatsappgraphversion",
                "whatsappphonenumberid", "whatsappaccesstoken", "whatsappverifytoken",
            }
            if any(key.replace("_", "").lower() in forbidden for key in data):
                raise ValueError("Messaging provider configuration must be set on the backend")
        return data