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
    config: dict,
    rois:dict = None
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

            return build_imaging_selection_resource_for_rois(
                first_ds=first_ds,
                instance_data=instance_data,
                patient=patient,
                study=study,
                config=config,
                rois=rois,
                series_uid=series_uid
            )     
            
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


def build_imaging_selection_resource_for_rois(
    first_ds: DicomJsonProxy,
    instance_data: any,
    patient: Patient,
    study: imagingstudy.ImagingStudy,
    config: dict,
    rois: dict,
    series_uid: str
) -> list[imagingselection.ImagingSelection]:

    if study is None:
        raise ValueError("No ImagingStudy available")

    if patient is None:
        raise ValueError("No Patient available")

    if not first_ds:
        raise ValueError("Cannot create ImagingSelection without instances")

    selections = []

    sop_instance_uid = instance_data.get("uid")
    roi_list = rois.get(series_uid).get(sop_instance_uid, [])

    if not roi_list:
        logger.warning(
            f"No StructureSetROISequence found in RTSTRUCT "
            f"{sop_instance_uid}"
        )
        return selections

            # ---------------------------------------------------------
            # Create ONE ImagingSelection per ROI
            # ---------------------------------------------------------
    for roi in roi_list:


        roi_name = roi["roiname"]
        roi_number = roi["roinumber"]
        roi_color = roi["roicolor"]
        roi_identification_code = roi["roi_identification_code"]
        roi_observation_label = roi["roi_observation_label"]
        roi_interpreted_type = roi["roi_interpreted_type"]

        selection_id = config["id_function"](
            "ImagingSelection",
            first_ds,
            f"ROI:{roi_number}"
        )

        identifiers = []
        identifiers.append(
                    {
                        "use": "official",
                        "type": CodeableConcept(
                            coding=[{
                                "system": f"{config['racoon_url']}/identifier-types",
                                "code": "ROI",
                                "display": "Radiotherapy structure ROI identifier"
                            }],
                            text="RTSTRUCT ROI identifier"
                        ),
                        "system": f"{config['racoon_url']}/roi-identifiers",
                        "value": f"{roi_name}"
                    }
        )

        extension = []
        if roi_identification_code is not None:
            extension.append({
                    "url": f"{config['racoon_url']}/fhir/StructureDefinition/rt-roi-identification-code",
                    "valueCodeableConcept": CodeableConcept(
                                    coding=[
                                        Coding(
                                                system=roi_identification_code["coding_scheme_designator"],
                                                code=roi_identification_code["code_value"],
                                                display=roi_identification_code["code_meaning"]
                                        )
                                    ]
                                )
                    
                }            ),

        if roi_observation_label is not None and roi_interpreted_type is not None:
            extension.append({
                    "url": "https://racoon.com/fhir/StructureDefinition/rt-roi-interpreted-type",
                    "valueCodeableConcept":  CodeableConcept(
                                    coding=[
                                        Coding(
                                                system=f"{config['racoon_url']}/fhir/CodeSystem/roi-interpreted-types",
                                                code=roi_interpreted_type,
                                                display=roi_observation_label
                                        )
                                    ]
                                )
                }            ),

        selection = imagingselection.ImagingSelection(

            id=selection_id,
            status="available",
            code=
                CodeableConcept(
                    coding=[
                        Coding(
                            system="http://dicom.nema.org/resources/ontology/DCM",
                            code="RTSTRUCT",
                            display="RT Structure Set"
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

            studyUid=str(first_ds.get('StudyInstanceUID')),

            seriesUid=str(first_ds.get('SeriesInstanceUID')),

            instance=[
                {
                    "uid": sop_instance_uid,

                    "subset": [f"{roi_number}"],
                    "sopClass": instance_data["sopClass"],

                    **(
                        {"number": instance_data["number"]}
                        if "number" in instance_data
                        else {}
                    )
                }
            ]
    
        )

        if len(identifiers) > 0:
            selection.identifier = identifiers
        if len(extension) > 0:
            selection.extension = extension

        selections.append(selection)

    return selections
