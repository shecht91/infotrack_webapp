import os
import requests
import aiohttp
import asyncio
import certifi
import ssl
import json
import streamlit as st
import regex

ssl_context = ssl.create_default_context(cafile=certifi.where())

# Initialize session state for data persistence
if "one_legal_case_info" not in st.session_state:
    st.session_state.one_legal_case_info = {
        "CaseNumber": "",
        "TrackingID": "",
        "CourtName": "",
        "ComplaintID": "",
        "ComplaintFiled": "",
        "CaseTitle": "",
        "Plaintiff": {
            "FullName": "",
            "Status": "",
            "PartyId": [],
            "OrganizationName": "",
            "FirstName": "",
            "LastName": "",
            "MiddleName": "",
            "Address": "",
            "Address2": "",
            "City": "",
            "State": "",
            "PostalCode": "",
            "Country": "",
            "PhoneNumber": "",
            "EmailAddress": ""
        },
        "Defendants": [],
        "Plaintiffs": [],
        "Attorneys": [],
        "Judgment": ""
    }

# Authentication variables
st.session_state.clientid = st.secrets["CLIENT_ID"]
st.session_state.clientsecret = st.secrets["CLIENT_SECRET"]
st.session_state.retailercode = st.secrets["RETAILER_CODE"]

# Input fields for user credentials
st.session_state.username = st.text_input("Username")
st.session_state.password = st.text_input("Password", type="password")

if "clientref" not in st.session_state:
    st.session_state.clientref = None
if "retailref" not in st.session_state:
    st.session_state.retailref = None
if "headers" not in st.session_state:
    st.session_state.headers = None
if "fileids" not in st.session_state:
    st.session_state.fileids = []

# Case Details Form
st.header("Case Details")
st.session_state.one_legal_case_info["CaseNumber"] = st.text_input("Case Number", key="one_legal_case_info.CaseNumber")

async def get_token(username, password, clientid, clientsecret):
    data = {
        'grant_type': 'password',
        'Username': username,
        'Password': password,
    }
    async with aiohttp.ClientSession() as session:
        auth = aiohttp.BasicAuth(clientid, clientsecret)
        async with session.post('https://auth.infotrack.com/connect/token', auth=auth,
                               headers={"Content-Type": "application/x-www-form-urlencoded"}, data=data, ssl=ssl_context) as response:
            data2 = await response.json(content_type=None)
            if "access_token" not in data2:
                return "bad_login"
            else:
                access_token = data2['access_token']
                headers = {"Authorization": f"Bearer {access_token}"}
                return headers

# Function to handle InfoTrack login
def login_infotrack(username, password, clientid, clientsecret):
    headers = asyncio.run(get_token(username, password, clientid, clientsecret))
    if headers != "bad_login":
        st.success("Login Successful.")
        return headers
    else:
        st.error("Login failed. Please try entering your username and password again.")
        quit()

# Function to upload a file
def upload_file():
    uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")
    if uploaded_file:
        try:
            upload(uploaded_file)
            st.success("File uploaded successfully.")
        except:
            st.error("Upload failed. Try again later.")

def update_case_details():
    courtdetails = [
        {"RegistryLocation": "lasc", "CaseNumber": st.session_state.one_legal_case_info['CaseNumber'], "RegistryCourt": "lasc",
         "FillingParties": [{"Role": "Defendant", "Address": {"StreetAddress1": "", "Suburb": "", "State": "", "PostCode": ""}},
                            {"Role": "Plaintiff", "Address": {"StreetAddress1": "", "Suburb": "", "State": "", "PostCode": ""},
                             "Individual": {"GivenName": st.session_state.one_legal_case_info["Plaintiff"]["FirstName"],
                                            "Surname": st.session_state.one_legal_case_info["Plaintiff"]["LastName"]}}]
         }]
    lawyers = [{"FirstName": "", "LastName": "", "Email": ""}]
    lawyerdetail = {"ContactDetails": [{"Individual": {"GivenName": "", "Surname": "", "Email": ""}}]}
    return lawyerdetail, courtdetails, lawyers

async def mapping(lawyerdetail, courtdetails, lawyers, clientref, retailref, fileids, headers, session):
    data = {
        "ClientReference": clientref,
        "RetailerReference": retailref,
        "MappingAttachments": fileids,
        "LawyerDetail": lawyerdetail,
        "State": "CA",
        "CourtDetails": courtdetails,
        "Lawyers": lawyers,
        "MatterType": "eFile: Civil Limited",
        "EntryPoint": "CA/CourtFiling/CaseSearch/Search"
    }
    async with session.post('https://search.infotrack.com/secure/api/v1/mapping', headers=headers, data=data, ssl=ssl_context) as response:
        data2 = await response.json(content_type=None)
        mapping_url = data2["Url"]
        fileids.clear()
        return mapping_url

async def login_to_efile_CA(mapping_url, session):  # this step is required to scrape the case info. You do not need this function if you are just trying to e-file.
    async with session.get(mapping_url, ssl=ssl_context) as response:
        html_content = await response.text()
        if '<title>InfoTrack | E-Filing Login</title>' in html_content:
            return 'fail'

async def retrieve_case_tracking_id(clientref, session, headers):
    data = {'location': 'lasc', 'locationName': 'Los Angeles Superior Court',
            'courtLocationCode': '10|jti|losangeles', 'caseType': '', 'firstName': '', 'middleName': '',
            'lastName': '', 'businessName': '',
            'isBusinessOrAgency': 'false', 'caseNumber': clientref, 'searchType': 'Number',
            'isUnlawfulDetainerSearch': 'false', 'udCaseSearch': '', 'courtId': 'lasc'}
    async with session.post('https://search.infotrack.com/secure/api/courtfilingla/court/cases', headers=headers,
                            data=data, ssl=ssl_context) as response:
        search = await response.json(content_type=None)
        if "ExistingCases" not in search or not search["ExistingCases"]:
            return "no case", "no case"
        caseid = search["ExistingCases"][0]["CaseTrackingId"]
        casenum = search["ExistingCases"][0]["CaseNumber"]
        return caseid, casenum

async def open_case(caseid, casenum, session, headers):
    data = {'caseTrackingId': caseid, 'courtName': 'lasc', 'caseNumber': casenum, 'apiType': '1'}
    async with session.get('https://integrated.infotrack.com/CA/CourtFiling/ExistingCase/New', headers=headers,
                            data=data, ssl=ssl_context) as response:
        testopen_case = await response.text()
        take_json_case_info = regex.search(r'\{"TylerExistingCaseModel":.*,"OneLegalExistingCaseModel":null,',
                                           str(testopen_case))
        if not take_json_case_info:
            return "no case"
        json_case_info = take_json_case_info.group().replace(',"OneLegalExistingCaseModel":null,', '}')
        case_info = json.loads(json_case_info)
        return case_info

async def scrape_case_info(mapping_url, clientref, session, headers):
    result = await login_to_efile_CA(mapping_url, session)
    if result == 'fail':
        return 'fail', 'fail', 'fail'
    case_id, case_num = await retrieve_case_tracking_id(clientref, session, headers)
    if case_id == 'no case':
        return 'no case', 'no case', 'no case'
    case_info = await open_case(case_id, case_num, session, headers)
    return case_id, case_num, case_info

# Function to search for a case number
async def search_case_number(fileids, headers):
    search_casenumber = st.session_state.one_legal_case_info["CaseNumber"]
    retailref = "Paul"
    clientref = search_casenumber.upper()
    lawyerdetail, courtdetails, lawyers = update_case_details()
    async with aiohttp.ClientSession() as session:
        mapping_url = await mapping(lawyerdetail, courtdetails, lawyers, clientref, retailref, fileids, headers, session)
        st.session_state.mapping_url = mapping_url
        caseid, casenum, case_info = await scrape_case_info(mapping_url, clientref, session, headers)
        if casenum == 'fail':
            st.error("Couldn't login to eFile CA. Please login to OneLegal and then go here:  \n https://platform.onelegal.com/AddEfm"
                     "  \n and make sure that your account is connected to eFile CA.")
            quit()
        if caseid == 'no case' or case_info == 'no case':
            st.error("No case was found. Make sure the case number is entered correctly. If it was, the site may just be down. Try again later.")
            quit()
    st.session_state.one_legal_case_info["CaseNumber"] = casenum
    st.session_state.one_legal_case_info["TrackingID"] = caseid
    st.session_state.one_legal_case_info["CourtName"] = case_info["LaExistingCaseModel"]["CourtName"]
    st.session_state.one_legal_case_info["ComplaintID"] = case_info["LaExistingCaseModel"]["Complaints"][0]["Id"]
    Parties = case_info["LaExistingCaseModel"]["Complaints"][0]["ExistingParties"]
    st.session_state.one_legal_case_info["CaseTitle"] = case_info["LaExistingCaseModel"]["CaseTitle"]
    all_plaintiffs = st.session_state.one_legal_case_info["CaseTitle"].split(" vs ")[0]
    st.session_state.one_legal_case_info["ComplaintFiled"] = regex.search(r'\d{1,2}\/\d{1,2}\/\d{2,4}',
                 case_info["LaExistingCaseModel"]["Complaints"][0]["CaseTitle"]).group()
    st.session_state.one_legal_case_info["Plaintiffs"].clear()
    st.session_state.one_legal_case_info["Defendants"].clear()
    Plaintiff_Variables = ["FullName", "Status", "OrganizationName", "FirstName", "LastName", "MiddleName",
                           "Address", "Address2", "City", "State", "PostalCode", "Country", "PhoneNumber",
                           "EmailAddress"]
    Defendant_Variables = ["FullName", "Status", "HasFeeWaiver", "PartyId", "OrganizationName", "FirstName", "LastName",
                           "MiddleName", "Address", "Address2", "City", "State", "PostalCode", "Country", "PhoneNumber",
                           "EmailAddress"]
    for i in range(len(Parties)):
        if Parties[i]["PartyTypeId"] != "PLAIN":
            Defendant = {key: Parties[i][key] for key in Defendant_Variables}
            st.session_state.one_legal_case_info["Defendants"].append(Defendant)
        elif Parties[i]["PartyTypeId"] == "PLAIN":
            Plaintiff = {key: Parties[i][key] for key in Plaintiff_Variables}
            st.session_state.one_legal_case_info["Plaintiffs"].append(Plaintiff)
            st.session_state.one_legal_case_info["Plaintiff"]["PartyId"].append(Parties[i]["PartyId"])
    Attorneys = case_info["LaExistingCaseModel"]["ExistingAttorneys"]
    Attorneys_Variables = ["BarNumber", "CorporateName", "FirstName", "LastName", "MiddleName", "Suffix", "Address",
                           "Address2", "City", "State", "PostalCode", "Country", "PostalBoxNumber", "PhoneNumber",
                           "EmailAddress", ]
    st.session_state.one_legal_case_info["Attorneys"].clear()
    for i in range(len(Attorneys)):
        Attorney = {key: Attorneys[i][key] for key in Attorneys_Variables}
        if Attorneys[i]["RepresentingPartiesIds"] != None:
            if any(party_id in Attorneys[i]["RepresentingPartiesIds"] for party_id in
                   st.session_state.one_legal_case_info["Plaintiff"]["PartyId"]):
                Attorney["Representing"] = "Plaintiff"
            else:
                Attorney["Representing"] = "Defendant"
        else:
            Attorney["Representing"] = "Former Attorney"
        st.session_state.one_legal_case_info["Attorneys"].append(Attorney)
    st.session_state.one_legal_case_info["CaseTitle"] = case_info["LaExistingCaseModel"]["CaseTitle"]
    try:
        st.session_state.one_legal_case_info["Judgment"] = case_info["LaExistingCaseModel"]["CaseJudgments"][0]["JudgmentTitle"]
    except:
        st.session_state.one_legal_case_info["Judgment"] = case_info["LaExistingCaseModel"]["CaseJudgments"]
    case_title_display = "**Case Title:**\n" + st.session_state.one_legal_case_info["CaseTitle"]
    st.markdown(case_title_display)
    court_name_display = "**Court Name:**\n" + st.session_state.one_legal_case_info["CourtName"]
    st.markdown(court_name_display)
    complaint_filed_date_display = "**Complaint Filing Date:**\n" + st.session_state.one_legal_case_info["ComplaintFiled"]
    st.markdown(complaint_filed_date_display)
    status_display = "**Status:**\n"
    status_display += f"{st.session_state.one_legal_case_info["Judgment"]}\n\n"
    st.markdown(status_display)
    plaintiff_display = "**Plaintiff Details:**\n"

    for plaintiff in st.session_state.one_legal_case_info["Plaintiffs"]:
        name = plaintiff["FullName"] if plaintiff["FullName"] else plaintiff["OrganizationName"]
        status = plaintiff["Status"]
        address = plaintiff["Address"]
        address2 = plaintiff["Address2"]
        city = plaintiff["City"]
        state = plaintiff["State"]
        zipcode = plaintiff["PostalCode"]
        phone = plaintiff["PhoneNumber"]
        email = plaintiff["EmailAddress"]
        if address and city:
            plaintiff_info = f"""
    {name}, {status if status not in [None, 'None'] else ''}
    {address} {address2 if address2 not in [None, 'None'] else ''}
    {city}, {state if state not in [None, 'None'] else ''} {zipcode if zipcode not in [None, 'None'] else ''}
    Phone: {phone} Email: {email}
    """
        else:
            plaintiff_info = f"""
    {name}, {status if status not in [None, 'None'] else ''}
    Phone: {phone} Email: {email}
    """
        plaintiff_display += plaintiff_info + "\n"

    st.markdown(plaintiff_display)

    # Build and display defendants' details
    defendant_display = "**Defendant Details:**\n"
    for defendant in st.session_state.one_legal_case_info["Defendants"]:
        name = defendant["FullName"]
        status = defendant["Status"]
        fw = defendant["HasFeeWaiver"]
        address = defendant["Address"]
        address2 = defendant["Address2"]
        city = defendant["City"]
        state = defendant["State"]
        zipcode = defendant["PostalCode"]
        phone = defendant["PhoneNumber"]
        email = defendant["EmailAddress"]

        if address and city:
            defendant_info = f"""
    {name}, Status: {status}
    {address} {address2 if address2 not in [None, 'None'] else ''}
    {city}, {state if state not in [None, 'None'] else ''} {zipcode if zipcode not in [None, 'None'] else ''}
    Phone: {phone} Email: {email}
    Fee Waiver: {fw}
    """
        else:
            defendant_info = f"""
    {name}, Status: {status}
    Phone: {phone} Email: {email}
    Fee Waiver: {fw}
    """
        defendant_display += defendant_info + "\n"

    st.markdown(defendant_display)

    # Build and display attorneys' details
    attorney_display = "**Attorney Details:**\n"
    for attorney in st.session_state.one_legal_case_info["Attorneys"]:
        party = attorney["Representing"]
        sbn = attorney["BarNumber"]
        firm = attorney["CorporateName"]
        first = attorney["FirstName"]
        middle = attorney["MiddleName"]
        last = attorney["LastName"]
        suffix = attorney["Suffix"]
        address = attorney["Address"]
        address2 = attorney["Address2"]
        city = attorney["City"]
        state = attorney["State"]
        zipcode = attorney["PostalCode"]
        PO = attorney["PostalBoxNumber"]
        phone = attorney["PhoneNumber"]
        email = attorney["EmailAddress"]
        if address and city:
            attorney_info = f"""
    **{party}**
    {firm}
    {first} {middle if middle not in [None, 'None'] else ''} {last} {suffix if suffix not in [None, 'None'] else ''}, SBN: {sbn}
    {address} {address2 if address2 not in [None, 'None'] else ''}
    {city}, {state} {zipcode} {PO if PO not in [None, 'None'] else ''}
    Phone: {phone} Email: {email}
    """
        else:
            attorney_info = f"""
    **{party}**
    {firm}
    {first} {middle if middle not in [None, 'None'] else ''} {last} {suffix if suffix not in [None, 'None'] else ''}, SBN: {sbn}
    Phone: {phone} Email: {email}
    """
        attorney_display += attorney_info + "\n"

    st.markdown(attorney_display)

# Action buttons
if st.button("Login to InfoTrack"):
    st.session_state.headers = login_infotrack(st.session_state.username, st.session_state.password, st.session_state.clientid, st.session_state.clientsecret)

if st.button("Search Case Info"):
    asyncio.run(search_case_number(st.session_state.fileids, st.session_state.headers))

def upload(files_to_upload):
    if not files_to_upload:
        raise ValueError("No files to upload.")

    files = {
        os.path.splitext(file.name)[0]: (file.name, file, 'multipart/form-data')
        for file in files_to_upload
    }
    with requests.Session() as session:
        response = session.post(
            'https://search.infotrack.com/secure/api/v1/fileupload',
            headers=headers,
            files=files
        ).json()
        for file_uploaded in response.get("Files", []):
            fileids.append({"Id": file_uploaded["FileId"]})
        return response
