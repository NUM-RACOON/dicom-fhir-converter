import argparse
from time import sleep
from datetime import datetime 
import os


import requests

from dicom2fhir import dicom2fhir

from asgiref.sync import async_to_sync
from pathlib import Path


from asgiref.sync import async_to_sync
# wrapper function to process study
def process_study(root_path, output_path, save_json_file, fhir_server = None , sessionkey = None):
    dicom2fhir_config = {
        "dicom_timezone": "Europe/Berlin",  # Set the timezone for DICOM dates
        "generator": {
            "imaging_study": {
                "add_instances": True  # Do not add single instances, only series to the ImagingStudy
            },
            "observation": {
                "add_vital_signs": True  # Add vital signs Observations for body weight and height
            }
        }
    }

    try:
        bundle = async_to_sync(dicom2fhir.from_directory)(str(root_path),config=dicom2fhir_config)
    except Exception as e:
        print(f"Error processing DICOM directory: {e}")
        return  # Return early if processing fails

    # study_id = accession_nr
    # if accession_nr is None:
    #     study_id = str(study_instance_uid)
    #     if study_instance_uid is None:
    #         raise ValueError(
    #             "No suitable ID in DICOM file available to set the identifier")



    # build imagingstudy bundle
    if bundle:
        # need to sent to FHIR
        if fhir_server is not None:
            response = requests.post(url=f'{fhir_server}',
                          data=  bundle.model_dump_json(),              
                           headers= {
                    "Content-type": "application/fhir+json",
                }, verify=False)

            print(response)
            # session = requests.Session()
            # response = session.post(
            #     fhir_server,
            #     result_bundle.json() ,
            #     headers={
            #         "Content-type": "application/fhir+json",
            #     }
            # )
                # now we extract the patient_id that was returned to us
            response.raise_for_status()
            sleep(1)


        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if save_json_file == True:
            try:
                
                os.makedirs(output_path,exist_ok=True)
                output_path = os.path.join(output_path, sessionkey) if sessionkey else output_path
                os.makedirs(output_path,exist_ok=True)
                # print(output_path)
                study_id =bundle.entry[0].resource.id
                jsonfile = os.path.join(output_path , f"{study_id}_{timestamp}_bundle.json")
                with open(jsonfile, "w+") as outfile:
                    outfile.write(bundle.model_dump_json())
            except Exception:
                print("Unable to create ImagingStudy JSON-file (probably missing identifier)")
    else:
        if save_json_file == True:
            try:
                jsonfile = output_path + str(id) + "_imagingStudy.json"
                with open(jsonfile, "w+") as outfile:
                    outfile.write(bundle.json())
            except Exception:
                print("Unable to create ImagingStudy JSON-file (probably missing identifier)")
    #build device
    # if create_device and save_json_file == True:
    #     for dev in dev_list:
    #         dev_id = dev[1]
    #         dev_resource = dev[0]
    #         try:
    #             jsonfile = output_path + "Device_" + str(dev_id) + ".json"
    #             with open(jsonfile, "w+") as outfile:
    #                 outfile.write(dev_resource.json())
    #         except Exception:
    #             print("Unable to create device JSON-file")




DEFAULT_DICOM_PATH  = Path("./dicom_data")
DEFAULT_OUTPUT_PATH  = Path("./output")

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Process DICOM studies.")
    parser.add_argument(
        "-i", "--input",
        type=Path,
        default=DEFAULT_DICOM_PATH,
        help=f"Input DICOM directory (default: {DEFAULT_DICOM_PATH})"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Output directory (default: {DEFAULT_OUTPUT_PATH})"
    )

    args = parser.parse_args()

    dicom_path = args.input
    output_path = args.output



    if not dicom_path .is_dir():
        raise FileNotFoundError(f"Input directory not found: {dicom_path}")

    output_path.mkdir(parents=True, exist_ok=True)

    fhir_server_address = "http://10.250.8.80:8080/fhir/"  # Replace with your FHIR server address
    process_study(root_path=str(dicom_path), output_path=str(output_path), save_json_file=True, fhir_server=fhir_server_address, sessionkey=None)
