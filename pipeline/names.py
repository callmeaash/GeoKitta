"""Name parts for fictional owners, as (Latin, Devanagari)."""

MALE = [
    ("Ram", "राम"), ("Hari", "हरि"), ("Krishna", "कृष्ण"), ("Shyam", "श्याम"), ("Bikash", "विकास"),
    ("Suresh", "सुरेश"), ("Ramesh", "रमेश"), ("Dinesh", "दिनेश"), ("Rajesh", "राजेश"), ("Sunil", "सुनिल"),
    ("Anil", "अनिल"), ("Prakash", "प्रकाश"), ("Sanjay", "सञ्जय"), ("Bishnu", "विष्णु"), ("Gopal", "गोपाल"),
    ("Narayan", "नारायण"), ("Kiran", "किरण"), ("Rajendra", "राजेन्द्र"), ("Mahesh", "महेश"), ("Nabin", "नबिन"),
    ("Sagar", "सागर"), ("Bibek", "विवेक"), ("Sujan", "सुजन"), ("Roshan", "रोशन"), ("Dipak", "दीपक"),
    ("Ganesh", "गणेश"), ("Mohan", "मोहन"), ("Prem", "प्रेम"), ("Arjun", "अर्जुन"), ("Bijay", "विजय"),
]
FEMALE = [
    ("Sita", "सीता"), ("Gita", "गीता"), ("Laxmi", "लक्ष्मी"), ("Sarita", "सरिता"), ("Anita", "अनिता"),
    ("Sunita", "सुनिता"), ("Kamala", "कमला"), ("Radha", "राधा"), ("Parbati", "पार्वती"), ("Maya", "माया"),
    ("Sabina", "सबिना"), ("Rita", "रीता"), ("Sushila", "सुशीला"), ("Bimala", "विमला"), ("Asha", "आशा"),
    ("Pooja", "पूजा"), ("Srijana", "सृजना"), ("Manisha", "मनिषा"), ("Nirmala", "निर्मला"), ("Shanti", "शान्ति"),
    ("Durga", "दुर्गा"), ("Saraswati", "सरस्वती"), ("Anju", "अञ्जु"), ("Rekha", "रेखा"), ("Usha", "उषा"),
    ("Kabita", "कविता"), ("Bina", "बिना"), ("Sangita", "संगीता"), ("Menuka", "मेनुका"), ("Samjhana", "सम्झना"),
]
MALE_MIDDLE = [("Bahadur", "बहादुर"), ("Prasad", "प्रसाद"), ("Kumar", "कुमार"), ("Raj", "राज"), ("Lal", "लाल"),
               ("Man", "मान")]
FEMALE_MIDDLE = [("Kumari", "कुमारी"), ("Devi", "देवी"), ("Maya", "माया")]
SURNAMES = [
    ("Shrestha", "श्रेष्ठ"), ("Maharjan", "महर्जन"), ("Tamang", "तामाङ"), ("Gurung", "गुरुङ"), ("Rai", "राई"),
    ("Thapa", "थापा"), ("Adhikari", "अधिकारी"), ("Sharma", "शर्मा"), ("Karki", "कार्की"), ("Bhattarai", "भट्टराई"),
    ("Pradhan", "प्रधान"), ("Shakya", "शाक्य"), ("Bajracharya", "वज्राचार्य"), ("Dangol", "डंगोल"),
    ("Manandhar", "मानन्धर"), ("Joshi", "जोशी"), ("Khadka", "खड्का"), ("Basnet", "बस्नेत"), ("Poudel", "पौडेल"),
    ("Koirala", "कोइराला"), ("Pandey", "पाण्डे"), ("Rana", "राणा"), ("KC", "केसी"), ("Lama", "लामा"),
    ("Magar", "मगर"), ("Sherpa", "शेर्पा"), ("Tuladhar", "तुलाधर"), ("Rajbhandari", "राजभण्डारी"),
    ("Singh", "सिंह"), ("Yadav", "यादव"), ("Dahal", "दाहाल"), ("Ghimire", "घिमिरे"), ("Neupane", "न्यौपाने"),
    ("Subedi", "सुवेदी"), ("Aryal", "अर्याल"), ("Bista", "विष्ट"), ("Silwal", "सिलवाल"), ("Kafle", "काफ्ले"),
    ("Acharya", "आचार्य"), ("Giri", "गिरी"),
]

# Common alternative spellings, used to plant near-duplicate owners for the duplicate warning
VARIANTS = {
    "Shrestha": "Shreshtha", "Laxmi": "Lakshmi", "Bishnu": "Vishnu", "Bikash": "Vikash", "Maharjan": "Maharajan",
    "Poudel": "Paudel", "Bhattarai": "Bhattrai", "Pradhan": "Pradan", "Neupane": "Neupaney",
    "Rajbhandari": "Rajbhandary", "Manandhar": "Manandar", "Dipak": "Deepak", "Pooja": "Puja", "Kabita": "Kavita",
    "Bijay": "Vijay", "Nabin": "Navin", "Bibek": "Vivek", "Sanjay": "Sanjaya", "Parbati": "Parvati",
    "Pandey": "Pande", "Bahadur": "Bahaddur", "Kumari": "Kumary",
}

COMPANY_WORDS = ["Himal", "Kanchan", "Sagun", "Shikhar", "Samriddhi", "Pragati", "Unnati", "Saptarangi", "Nilgiri",
                 "Gaurishankar", "Shubha", "Navaratna"]
COMPANY_KINDS = ["Traders", "Builders", "Housing", "Enterprises", "Suppliers", "Holdings"]
BANKS = ["Nilgiri Demo Bank", "Shikhar Demo Bank", "Kanchan Demo Bank", "Pragati Demo Finance",
         "Unnati Demo Cooperative"]
