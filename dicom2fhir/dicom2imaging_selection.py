import logging

from fhir.resources.reference import Reference
from fhir.resources.coding import Coding
from fhir.resources.codeableconcept import CodeableConcept
from fhir.resources.patient import Patient
from fhir.resources import imagingstudy
from fhir.resources import imagingselection

from dicom2fhir.dicom_json_proxy import DicomJsonProxy

logger = logging.getLogger(__name__)

RTSTRUCT_SOP_CLASS_UID = "1.2.840.10008.5.1.4.1.1.481.3"
def is_rtstruct(instance_data: dict) -> bool:
    sop_class = instance_data.get("sopClass")

    if sop_class is None:
        return False

    return sop_class.code == f"urn:oid:{RTSTRUCT_SOP_CLASS_UID}"


def build_imaging_selection_resource(
    instances: list[DicomJsonProxy],#dicom instances as json...
    patient: Patient,
    study : imagingstudy.ImagingStudy,
    first_ds: DicomJsonProxy,
    config: dict
) -> list[imagingselection.ImagingSelection]:


    if study is None:
        raise ValueError("No ImagingStudy available")

    if patient is None:
        raise ValueError("No Patient available")

    if not instances:
        raise ValueError("Cannot create ImagingSelection without instances")

    selections = []

    for series_uid, series_instances in instances.items():
        instance_list = []
        for sop_uid, instance_data in series_instances.items():

            if not is_rtstruct(instance_data):
                continue      
            
            item = {
                 "uid": sop_uid
             }
            if "sopClass" in instance_data:
                item["sopClass"] = instance_data["sopClass"]

            if "number" in instance_data:
                item["number"] = instance_data["number"]

            if "title" in instance_data:
                item["title"] = instance_data["title"]

            if "extension" in instance_data:
                item["extension"] = instance_data["extension"]

            instance_list.append(item)

        if len(instance_list) == 0:
            logger.warning(f"No valid instances found for series {series_uid}. Skipping ImagingSelection creation for this series.")
            continue

        selection = imagingselection.ImagingSelection(
            id=config["id_function"](
                "ImagingSelection",
                first_ds
            ),

            status="available",

            code=
                CodeableConcept(
                    coding=[
                        Coding(
                            system="http://dicom.nema.org/resources/ontology/DCM",
                            code="113014",
                            display="DICOM Key Object Selection"
                        )
                    ]
                ),
            

            subject=Reference(
                reference=f"Patient/{patient.id}"
            ),

            derivedFrom=[
                Reference(
                    reference=f"ImagingStudy/{study.id}"
                )
            ],

            studyUid=str(first_ds.StudyInstanceUID),

            seriesUid=series_uid,

            instance=instance_list
            )

        selections.append(selection)
        

    return selections

