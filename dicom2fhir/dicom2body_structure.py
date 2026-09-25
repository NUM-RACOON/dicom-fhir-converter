import logging

from fhir.resources.reference import Reference
from fhir.resources.coding import Coding
from fhir.resources.codeableconcept import CodeableConcept
from fhir.resources.patient import Patient
from fhir.resources import imagingstudy
from fhir.resources import imagingselection
from dicom2fhir.dicom_json_proxy import DicomJsonProxy
from dicom2fhir.helpers import get_or

logger = logging.getLogger(__name__)


def build_body_structure_for_roi(
    patient,
    first_ds,
    config,
    roi,
    sop_instance_uid
):
    """
    Build one FHIR R6 BodyStructure resource for one RTSTRUCT ROI.

    Returns:
        dict:
            FHIR BodyStructure resource as a dictionary.
    """

    if patient is None:
        raise ValueError("No Patient available")

    if not first_ds:
        raise ValueError("No DICOM dataset available")

    roi_number = roi.get("roinumber")
    roi_name = roi.get("roiname")

    roi_observation_label = roi.get("roi_observation_label")
    roi_interpreted_type = roi.get("roi_interpreted_type")

    if roi_number is None:
        raise ValueError("RTSTRUCT ROI has no ROI number")

    roi_number = int(roi_number)

    # -------------------------------------------------
    # BodyStructure ID
    # -------------------------------------------------
    body_structure_id = config["id_function"](
        "BodyStructure",
        first_ds,
        f"ROI:{roi_number}"
    )

    # -------------------------------------------------
    # DICOM RTSTRUCT identifier
    # -------------------------------------------------
    identifier = {
        "use": "usual",
        "system": "urn:dicom:uid",
        "value": f"urn:oid:{sop_instance_uid}"
    }

    # -------------------------------------------------
    # Morphology is wrong, needs snomed terminology not present in rtstruct
    # -------------------------------------------------
    morphology = None
    location = None
    location_qualifier = None

    # if (
    #     roi_interpreted_type is not None
    #     or roi_observation_label is not None
    # ):
    #     morphology_coding = {}

    #     if roi_interpreted_type is not None:
    #         morphology_coding["code"] = str(
    #             roi_interpreted_type
    #         )

    #     if roi_observation_label is not None:
    #         morphology_coding["display"] = str(
    #             roi_observation_label
    #         )

    #     morphology = {
    #         "coding": [morphology_coding]
    #     }

    #     if roi_observation_label:
    #         morphology["text"] = str(
    #             roi_observation_label
    #         )
    #     elif roi_interpreted_type:
    #         morphology["text"] = str(
    #             roi_interpreted_type
    #         )

    #example of morphology and location, bot not present in rTSTRUCT
    # "morphology": {
    #     "coding": [
    #     {
    #         "system": "http://snomed.info",
    #         "code": "228793007",
    #         "display": "Planning target volume for radiation therapy (descriptor)"
    #     }
    #     ],
    #     "text": "Clinical Target Volume (CTV)"
    # },
    # "location": {
    #     "coding": [
    #     {
    #         "system": "http://snomed.info",
    #         "code": "41216001",
    #         "display": "Prostatic structure (body structure)"
    #     }
    #     ],
    #     "text": "Prostata"
    # },





    # -------------------------------------------------
    # BodyStructure
    # -------------------------------------------------
    body_structure = {
        "resourceType": "BodyStructure",
        "id": body_structure_id,
        "identifier": [identifier],
        "active": True,
        "patient": {
            "reference": f"Patient/{patient.id}"
        }
    }

    if morphology is not None:
        body_structure["morphology"] = morphology
    if location is not None:
        body_structure["location"] = location
    if location_qualifier is not None:
        body_structure["locationQualifier"] = location_qualifier


    if roi_name:
        body_structure["description"] = str(roi_name)

    # -------------------------------------------------
    # DICOM RTSTRUCT ROI Number
    # -------------------------------------------------
    body_structure["extension"] = [
        {
            "url": (
                f"{config['racoon_url']}/fhir/"
                "StructureDefinition/rt-roi-number"
            ),
            "valueInteger": roi_number
        }
    ]

    if (roi_interpreted_type is not None):
        body_structure["extension"].append(
            {
                "url": (
                    f"{config['racoon_url']}/fhir/"
                    "StructureDefinition/rt-roi-interpreted-type"
                ),
                "valueString": str(roi_interpreted_type)
            }
        )
    if(roi_observation_label is not None):
        body_structure["extension"].append(
            {
                "url": (
                    f"{config['racoon_url']}/fhir/"
                    "StructureDefinition/rt-roi-observation-label"
                ),
                "valueString": str(roi_observation_label)
            }
        )

    return body_structure