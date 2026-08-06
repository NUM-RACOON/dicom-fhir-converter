import logging

from fhir.resources.reference import Reference
from fhir.resources.coding import Coding
from fhir.resources.codeableconcept import CodeableConcept
from fhir.resources.patient import Patient
from fhir.resources import imagingstudy
from fhir.resources import imagingselection

from dicom2fhir.dicom_json_proxy import DicomJsonProxy

logger = logging.getLogger(__name__)

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
    
    for series_uid, instances in instances.items():

        instance_list = []

        for sop_uid, instance_data in instances.items():

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

