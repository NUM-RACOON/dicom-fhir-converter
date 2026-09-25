import json
import uuid
from fhir.resources import bundle
from fhir.resources import imagingstudy
from fhir.resources import patient
from fhir.resources import device
from fhir.resources.reference import Reference
from fhir.resources.meta import Meta
from fhir.resources.codeableconcept import CodeableConcept
from fhir.resources.codeablereference import CodeableReference
#from pydicom import dataset
import logging
from dicom2fhir.dicom2fhirutils import gen_coding, SOP_CLASS_SYS, ACQUISITION_MODALITY_SYS, gen_bodysite_coding, gen_accession_identifier, gen_studyinstanceuid_identifier, dcm_coded_concept, gen_procedurecode_array, gen_started_datetime, gen_reason
from dicom2fhir.dicom2patient import build_patient_resource
from dicom2fhir.dicom2observation import build_observation_resources
from dicom2fhir.dicom2device import build_device_resource
from dicom2fhir.dicom2endpoint import build_endpoint_resource
from dicom2fhir.helpers import get_or, get_rtstruct_rois
from dicom2fhir.dicom_json_proxy import DicomJsonProxy
# extensions
from dicom2fhir.extensions import extension_contrast, extension_CT, extension_instance, extension_MG_CR_DX, extension_MR, extension_NM, extension_PT, extension_reason

from dicom2fhir.dicom2imaging_selection import build_imaging_selection_resource
logger = logging.getLogger(__name__)

class Dicom2FHIRBundle():

    def __init__(self, config: dict = {}):
        """
        Initialize the Dicom2FHIRBundle with an optional configuration.
        """
        self.study: imagingstudy.ImagingStudy | None = None

        self.first_ds: DicomJsonProxy | None = None
        self.series = {}
        self.instances = {}
        # Device
        #self.device: device.Device | None = None
        # Patient
        self.pat: patient.Patient | None = None
        self.obs = []
        self.config = config
        self.devices = {}
        self.rtstructInstances ={}
        
        
    def add(self, ds: DicomJsonProxy):
        """
        Add a DICOM dataset to the ImagingStudy.
        """
        if not isinstance(ds, DicomJsonProxy):
            raise TypeError("Expected a DicomJsonProxy object")

        # is first instance?
        if self.study is None:
            self.first_ds = ds
            #self.device = build_device_resource(ds, self.config)
            self.pat = build_patient_resource(ds, self.config)
            self._create_imaging_study(ds)
            if get_or(self.config, "generator.observation.add_vital_signs", True):
                self.obs = build_observation_resources(ds, self.pat, self.study, self.config) or []

        self._add_imaging_study_series(ds)
        self._add_instance(ds)

    def _create_imaging_study(self, ds):

        study_data = {}
        study_data["resource_type"] = "ImagingStudy"
        study_data["meta"] = Meta(profile=[
            "https://www.medizininformatik-initiative.de/fhir/ext/modul-bildgebung/StructureDefinition/mii-pr-bildgebung-bildgebungsstudie"])
        study_data["id"] = self.config['id_function']("ImagingStudy", ds)
        study_data["status"] = "available"
        
        if ds.non_empty("StudyDescription"):
            study_data["description"] = str(ds.StudyDescription)
        
        study_data["identifier"] = []
        if ds.non_empty("AccessionNumber"):
            study_data["identifier"].append(gen_accession_identifier(str(ds.AccessionNumber)))
        if ds.non_empty("StudyInstanceUID"):
            study_data["identifier"].append(gen_studyinstanceuid_identifier(str(ds.StudyInstanceUID)))

        # Set the patient reference
        study_data["subject"] = Reference.model_construct(reference=f"Patient/{self.pat.id}") if self.pat else None

        # procedure codes
        if ds.non_empty("ProcedureCodeSequence"):
            procedures = dcm_coded_concept(ds.ProcedureCodeSequence)
            study_data["procedureCode"] = gen_procedurecode_array(procedures)        

        if ds.non_empty("StudyDate") and ds.non_empty("StudyTime"):
            study_data["started"] = gen_started_datetime(str(ds.StudyDate), str(ds.StudyTime), self.config["dicom_timezone"])

        # reason codes - read from each ReferencedRequestSequence ITEM (the
        # Reason* attributes live inside the sequence items, not at top level)
        if ds.non_empty("ReferencedRequestSequence"):
            reason_codes = []
            for seq in ds.ReferencedRequestSequence:

                reason = None
                reasonStr = None

                if seq.non_empty("ReasonForRequestedProcedureCodeSequence"):
                    reason = dcm_coded_concept(seq.ReasonForRequestedProcedureCodeSequence)
                if seq.non_empty("ReasonForTheRequestedProcedure"):
                    reasonStr = str(seq.ReasonForTheRequestedProcedure)
                rc = gen_reason(reason, reasonStr)
                if rc:
                    reason_codes.extend(rc)
            if reason_codes:
                study_data["reasonCode"] = reason_codes
        
        study_extensions = []
        # reason extension
        e_reason = extension_reason.create_extension(ds)
        if e_reason is not None:
            study_extensions.append(e_reason)

        # only set when non-empty - avoids "extension": [] noise in the output
        if study_extensions:
            study_data["extension"] = study_extensions

        study_data["numberOfSeries"] = 0
        study_data["numberOfInstances"] = 0

        # instantiate study here, when all required fields are available
        self.study = imagingstudy.ImagingStudy(**study_data)
        
    def _add_imaging_study_series(self, ds: DicomJsonProxy):

        series_instance_uid = str(ds.SeriesInstanceUID)

        if series_instance_uid in self.series:
            return  # Series already exists

        # inti data container
        self.series[series_instance_uid] = {}
        self.series[series_instance_uid]["uid"] = series_instance_uid
        self.series[series_instance_uid]["numberOfInstances"] = 0

        if ds.non_empty("SeriesDescription"):
            self.series[series_instance_uid]["description"] = str(ds.SeriesDescription)

        if ds.non_empty("SeriesNumber"):
            try:
                series_number = int(float(str(ds.SeriesNumber)))  # handles both int and scientific notation

                if series_number >= 0 and series_number < 2147483647:
                    self.series[series_instance_uid]["number"] = series_number
                else:
                    # SeriesNumber is out of range, log a warning and store original value as extension
                    logger.warning(f"Invalid SeriesNumber {ds.SeriesNumber}: out of range")
                    self.series[series_instance_uid]["extension"] = [
                        {
                            "url": "http://dicom.nema.org/resources/ontology/DCM/series-number",
                            "valueString": str(ds.SeriesNumber)
                        }
                    ]
            except Exception as e:
                logger.warning(f"Invalid SeriesNumber {ds.SeriesNumber}: {e}")

        if ds.non_empty("Modality"):
            self.series[series_instance_uid]["modality"] = CodeableConcept(
                coding=[
                    gen_coding(
                        code=str(ds.Modality),
                        system=ACQUISITION_MODALITY_SYS
                    )
                ]
            )

        if series_instance_uid not in self.devices:
            device = build_device_resource(ds, self.config)
            self.devices[series_instance_uid] = device

        #added device as performer of the series if device information is available
        if device and device.id:
            self.series[series_instance_uid]["performer"] = [
                {
                    "actor": {
                        "reference": f"Device/{device.id}"
                    }
                }
            ]


        if ds.non_empty("SeriesDate") and ds.non_empty("SeriesTime"):
            self.series[series_instance_uid]["started"] = gen_started_datetime(
                str(ds.SeriesDate), str(ds.SeriesTime), self.config["dicom_timezone"]
            )

        if ds.non_empty("BodyPartExamined"):
            coding = gen_bodysite_coding(str(ds.BodyPartExamined))

            self.series[series_instance_uid]["bodySite"] = CodeableReference(
                concept=CodeableConcept(coding=[coding])
            )

        if ds.non_empty("Laterality"):
            self.series[series_instance_uid]["laterality"] = gen_coding(str(ds.Laterality))
        
        ########### extensions ##########
        series_extensions = []

        # MR extension
        if str(ds.Modality) == "MR":
            e_MR = extension_MR.create_extension(ds)
            if e_MR is not None:
                series_extensions.append(e_MR)
        # MG/DX/CR extension
        if (str(ds.Modality) == "MG") or (str(ds.Modality) == "DX") or (str(ds.Modality) == "CR"):
            e_MG = extension_MG_CR_DX.create_extension(ds)
            if e_MG is not None:
                series_extensions.append(e_MG)
        # CT extension
        if str(ds.Modality) == "CT":
            e_CT = extension_CT.create_extension(ds)
            if e_CT is not None:
                series_extensions.append(e_CT)
        # NM extension
        if str(ds.Modality) == "NM":
            e_NM = extension_NM.create_extension(ds)
            if e_NM is not None:
                series_extensions.append(e_NM)
        # PT extension
        if str(ds.Modality) == "PT":
            e_PT = extension_PT.create_extension(ds)
            if e_PT is not None:
                series_extensions.append(e_PT)

        # contrast extension
        e_con = extension_contrast.create_extension(ds)
        if e_con is not None:
            series_extensions.append(e_con)

        # APPEND to any extension already recorded for this series (e.g. the
        # out-of-range SeriesNumber extension) instead of clobbering it, and
        # only when non-empty.
        if series_extensions:
            self.series[series_instance_uid].setdefault("extension", []).extend(series_extensions)
    
    def _add_instance(self, ds: DicomJsonProxy):

        series_instance_uid = str(ds.SeriesInstanceUID)
        sop_instance_uid = str(ds.SOPInstanceUID)

        if series_instance_uid not in self.instances:
            self.instances[series_instance_uid] = {}

        if sop_instance_uid in self.instances[series_instance_uid]:
            # duplicate SOP instance: keep the first occurrence. (The previous
            # code crashed here - it called .as_json() on a plain dict.)
            logger.warning(
                "Duplicate SOPInstanceUID %s in series %s - skipping",
                sop_instance_uid, series_instance_uid,
            )
            return

        self.instances[series_instance_uid][sop_instance_uid] = {}
       
        self.instances[series_instance_uid][sop_instance_uid]["uid"] = sop_instance_uid
        self.instances[series_instance_uid][sop_instance_uid]["sopClass"] = gen_coding(
            code="urn:oid:" + ds.SOPClassUID,
            system=SOP_CLASS_SYS
        )

        if ds.non_empty("InstanceNumber"):
            self.instances[series_instance_uid][sop_instance_uid]["number"] = str(ds.InstanceNumber)

        try:
            if str(ds.Modality) == "SR":
                seq = ds.ConceptNameCodeSequence
                if isinstance(seq, list) and len(seq) > 0:
                    self.instances[series_instance_uid][sop_instance_uid]["title"] = str(seq[0].CodeMeaning)
            if(str(ds.Modality) == "RTSTRUCT") :
                rois = get_rtstruct_rois(ds)
                self.rtstructInstances.setdefault(series_instance_uid, {})[
                                                                sop_instance_uid
                                                            ] =  {
                                                                    "rois": rois,
                                                                    "frameOfReferenceUID": getattr(ds, "FrameOfReferenceUID", None),
                                                                    "approval_status": getattr(ds, "ApprovalStatus", None),
                                                                    "structre_set_label": getattr(ds, "StructureSetLabel", None),
                                                                    }
      
        except Exception:
            pass  # print("Unable to set instance title")

        # instance extension - only set when non-empty
        e_instance = extension_instance.create_extension(ds)
        if e_instance is not None:
            self.instances[series_instance_uid][sop_instance_uid]["extension"] = [e_instance]

    def _build_imaging_study(self) -> imagingstudy.ImagingStudy:
        """
        Build the ImagingStudy resource from the collected data.
        """
        if self.study is None:
            raise ValueError("No ImagingStudy data has been added")

        # Add series to the study
        self.study.series = []
        for series_uid, series_data in self.series.items():

            # only add sop instance data if configured
            if get_or(self.config, "generator.imaging_study.add_instances", False):
                series_data["instance"] = []
                for instance_uid, instance_data in self.instances.get(series_uid, {}).items():
                    series_data["instance"].append(imagingstudy.ImagingStudySeriesInstance(**instance_data))
                series_data["numberOfInstances"] = len(series_data["instance"])
            else:
                series_data["numberOfInstances"] = len(self.instances[series_uid])

            exstensions = []
            if(series_data['modality'].coding[0].code == "RTSTRUCT"):
                print("RTSTRUCT series found, adding ROI information to series extension")
                app_status = self.rtstructInstances.get(series_uid, {}).get(instance_uid, {}).get("approval_status", None)
                if(app_status is not None):
                    exstensions.append({
                        "url": f"{self.config['racoon_url']}/fhir/StructureDefinition/rtstruct-approval-status",
                        "valueCode": app_status
                    })
                structure_set_label = self.rtstructInstances.get(series_uid, {}).get(instance_uid, {}).get("structre_set_label", None)
                if(structure_set_label is not None):
                    exstensions.append({
                        "url": f"{self.config['racoon_url']}/fhir/StructureDefinition/rtstruct-structure-set-label",
                        "valueString": structure_set_label
                    })

            if len(exstensions) > 0:
                series_data["extension"] = exstensions

            # Create ImagingStudySeries object
            series = imagingstudy.ImagingStudySeries(**series_data)
            self.study.series.append(series)

        # Set the number of series and instances
        self.study.numberOfSeries = len(self.study.series)
        self.study.numberOfInstances = sum(s.numberOfInstances for s in self.study.series)

        # Set the modalities
        modality_set = {}

        for s in self.study.series or []:
            if s.modality and s.modality.coding:
                for coding in s.modality.coding:
                    modality_set[coding.code] = s.modality

        self.study.modality = list(modality_set.values())

        return self.study

    def create_bundle(self) -> bundle.Bundle:
        """
        Create the final transaction bundle.
        """

        def _to_entry(resource):
            return {
                #'fullUrl': f"urn:uuid:{resource.id}",
                'resource': resource,
                'request': {
                    'method': 'PUT',
                    'url': f"{resource.__resource_type__}/{resource.id}"
                }
            }

        if not self.study:
            raise ValueError("No ImagingStudy data has been added")

        # Build the ImagingStudy resource
        _study = self._build_imaging_study()       
        _imaging_selections = build_imaging_selection_resource(self.instances, self.pat, self.study, self.first_ds, self.config, self.rtstructInstances)

        entries = [
            _to_entry(_study),
            _to_entry(self.pat),
           # _to_entry(self.device),
        ]

        entries.extend(_to_entry(device) for device in self.devices.values() if device is not None)
        entries.extend(_to_entry(o) for o in self.obs) 
        entries.extend(_to_entry(sel) for sel in _imaging_selections)

        # Optional WADO-RS Endpoint (config: generator.endpoint.dicomweb_base_url).
        # Inserted BEFORE the ImagingStudy so transaction servers that validate
        # references in document order can resolve ImagingStudy.endpoint.
        dicomweb_base_url = get_or(self.config, "generator.endpoint.dicomweb_base_url", None)
        if dicomweb_base_url:
            _endpoint = build_endpoint_resource(dicomweb_base_url)
            _study.endpoint = [Reference.model_construct(reference=f"Endpoint/{_endpoint.id}")]
            entries.insert(0, _to_entry(_endpoint))

        # wrap entries in a transaction Bundle and return
        return bundle.Bundle.model_validate({
            'resourceType': 'Bundle',
            'type': "transaction",
            'id': str(uuid.uuid4()),
            'entry': entries
        })


    def create_bundle_r6(self) -> dict:
        """
        Create the final R6-compatible transaction bundle.
        """

        def _to_entry(resource):

            if isinstance(resource, dict):
                resource_dict = resource
            else:
                resource_dict = resource.model_dump(
                    mode="json",
                    exclude_none=True
                )

            resource_type = resource_dict["resourceType"]
            resource_id = resource_dict["id"]

            return {
                "resource": resource_dict,
                "request": {
                    "method": "PUT",
                    "url": f"{resource_type}/{resource_id}"
                }
            }
        if not self.study:
            raise ValueError("No ImagingStudy data has been added")

        # Build ImagingStudy
        _study = self._build_imaging_study()

        # Optional WADO-RS Endpoint
        dicomweb_base_url = get_or(
            self.config,
            "generator.endpoint.dicomweb_base_url",
            None
        )

        _endpoint = None

        if dicomweb_base_url:
            _endpoint = build_endpoint_resource(dicomweb_base_url)

            _study.endpoint = [
                Reference.model_construct(
                    reference=f"Endpoint/{_endpoint.id}"
                )
            ]

        # Build R6 ImagingSelections as dictionaries
        _imaging_selections, _body_structures = build_imaging_selection_resource(
            self.instances,
            self.pat,
            self.study,
            self.first_ds,
            self.config,
            self.rtstructInstances
        )

        # Build Bundle entries
        entries = []

        # Endpoint must appear before ImagingStudy
        if _endpoint is not None:
            entries.append(_to_entry(_endpoint))

        entries.append(_to_entry(_study))
        entries.append(_to_entry(self.pat))

        entries.extend(
            _to_entry(device)
            for device in self.devices.values()
            if device is not None
        )

        entries.extend(
            _to_entry(o)
            for o in self.obs
        )

        # R6 ImagingSelection dictionaries
        entries.extend(
            _to_entry(sel)
            for sel in _imaging_selections
        )
        entries.extend(
            _to_entry(bod)
            for bod in _body_structures
        )
        return {
            "resourceType": "Bundle",
            "type": "transaction",
            "id": str(uuid.uuid4()),
            "entry": entries
        }