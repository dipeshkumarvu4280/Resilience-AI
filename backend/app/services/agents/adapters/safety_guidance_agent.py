import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongodb import db_manager
from app.models.enums import (
    SeverityLevel,
    DestinationType,
    RouteStatus,
    GuidanceApprovalState,
    ResourceType,
    ResourceStatus,
)
from app.models.safety_guidance import (
    CitizenSafetyGuidance,
    VerifiedDestination,
    RouteDetails,
    HazardAvoidanceZone,
    generate_guidance_id,
    generate_secure_access_token,
)
from app.services.resource_matching import haversine_distance_km
from app.services.routing_service import RoutingService
from app.services.places_service import PlacesService
from app.services.notification.web_push_service import WebPushService

logger = logging.getLogger("resilience.agents.safety_guidance")


MULTILINGUAL_SAFETY_TEMPLATES = {
    "en": {
        "flood": {
            "actions": [
                "Move to highest accessible floor or elevated ground immediately.",
                "Avoid walking, wading, or driving through moving floodwaters.",
            ],
            "precautions": [
                "Turn off main electrical breaker and gas valve if safely accessible.",
                "Keep emergency kit, medications, and fully charged phone sealed in waterproof bag.",
            ],
        },
        "fire": {
            "actions": [
                "Evacuate building immediately via nearest safe ground exit; stay low under smoke.",
                "Close doors behind you to slow flame progression.",
            ],
            "precautions": [
                "Never use elevators during a structural fire emergency.",
                "Cover mouth and nose with a damp cloth if smoke is present.",
            ],
        },
        "landslide": {
            "actions": [
                "Move away from steep slopes, retaining walls, and compromised foundations.",
                "Listen for unusual cracking sounds, tumbling rocks, or sudden water surges.",
            ],
            "precautions": [
                "Avoid river valleys and low-lying drainage channels during active slope movement.",
            ],
        },
        "medical": {
            "actions": [
                "Keep patient still, calm, and warm; do not move injured persons unless immediate hazard threatens.",
                "Apply direct clean pressure to severe bleeding wounds.",
            ],
            "precautions": [
                "Clear access path for arriving emergency medical responders.",
            ],
        },
        "general": {
            "actions": [
                "Remain in a safe, sheltered location and await direct responder coordination.",
            ],
            "precautions": [
                "Keep communication lines clear for emergency responder updates.",
            ],
        },
        "dest_prefix": "Follow verified route towards {dest} ({dist:.1f} km).",
        "no_dest": "No safe evacuation destination is currently confirmed. Remain sheltered in place.",
        "route_advisory": "Route Advisory: {warning}",
    },
    "te": {
        "flood": {
            "actions": [
                "వెంటనే అత్యంత ఎత్తైన అంతస్తు లేదా ఎత్తైన ప్రదేశానికి చేరుకోండి.",
                "ప్రవహించే వరద నీటిలో నడవద్దు లేదా వాహనాలు నడపవద్దు.",
            ],
            "precautions": [
                "సురక్షితంగా వీలైతే ప్రధాన విద్యుత్ బ్రేకరు మరియు గ్యాస్ వాల్వ్ ఆపివేయండి.",
                "ఎమర్జెన్సీ కిట్, మందులు మరియు ఛార్జ్ చేసిన ఫోన్‌ను వాటర్‌ప్రూఫ్ బ్యాగ్‌లో ఉంచండి.",
            ],
        },
        "fire": {
            "actions": [
                "సమీపంలోని సురక్షిత మార్గం ద్వారా వెంటనే భవనాన్ని ఖాళీ చేయండి; పొగ కిందకి వంగి ఉండండి.",
                "మంటల వ్యాప్తిని తగ్గించడానికి మీ వెనుక తలుపులు మూసివేయండి.",
            ],
            "precautions": [
                "అగ్ని ప్రమాద సమయాల్లో ఎలివేటర్లను ఎప్పుడూ ఉపయోగించవద్దు.",
                "పొగ ఉంటే తడి గుడ్డతో ముక్కు మరియు నోటిని కప్పుకోండి.",
            ],
        },
        "landslide": {
            "actions": [
                "ఏటవాలు కొండలు, గోడలు మరియు బలహీనమైన పునాదుల నుండి దూరంగా వెళ్లండి.",
                "అసాధారణ శబ్దాలు, రాళ్ళు పడటం లేదా నీటి ప్రవాహాలను గమనించండి.",
            ],
            "precautions": [
                "వర్షాలు లేదా నేల కదలికల సమయంలో లోయలు మరియు పల్లపు కాలువల వద్ద ఉండకండి.",
            ],
        },
        "medical": {
            "actions": [
                "రోగిని ప్రశాంతంగా, వెచ్చగా ఉంచండి; అత్యవసర ప్రమాదం ఉంటే తప్ప క్షతగాత్రులను కదల్చవద్దు.",
                "తీవ్ర రక్తస్రావం జరుగుతున్న గాయాలపై శుభ్రమైన గుడ్డతో ఒత్తిడి ఉంచండి.",
            ],
            "precautions": [
                "అత్యవసర వైద్య సిబ్బంది రాక కోసం మార్గాన్ని స్పష్టంగా ఉంచండి.",
            ],
        },
        "general": {
            "actions": [
                "సురక్షితమైన ప్రదేశంలో ఉండి అత్యవసర ప్రతిస్పందన బృందం సూచనల కోసం వేచి ఉండండి.",
            ],
            "precautions": [
                "అత్యవసర రెస్పాండర్ అప్‌డేట్‌ల కోసం కమ్యూనికేషన్ లైన్లను సిద్ధంగా ఉంచండి.",
            ],
        },
        "dest_prefix": "{dest} వైపు నిర్ధారించబడిన మార్గాన్ని అనుసరించండి ({dist:.1f} కి.మీ).",
        "no_dest": "సురక్షిత తరలింపు కేంద్రం ఇంకా నిర్ధారించబడలేదు. సురక్షిత ప్రదేశంలోనే ఆశ్రయం పొందండి.",
        "route_advisory": "రహదారి హెచ్చరిక: {warning}",
    },
    "hi": {
        "flood": {
            "actions": [
                "तुरंत उच्चतम सुलभ मंजिल या ऊंचे स्थान पर जाएं।",
                "बहते बाढ़ के पानी में चलने या गाड़ी चलाने से बचें।",
            ],
            "precautions": [
                "सुरक्षित होने पर मुख्य बिजली ब्रेकर और गैस वाल्व बंद कर दें।",
                "इमरजेंसी किट, दवाएं और चार्ज फोन वाटरप्रूफ बैग में रखें।",
            ],
        },
        "fire": {
            "actions": [
                "निकटतम सुरक्षित निकास से तुरंत इमारत खाली करें; धुएं में नीचे झुककर रहें।",
                "आग के फैलाव को धीमा करने के लिए पीछे के दरवाजे बंद कर दें।",
            ],
            "precautions": [
                "आग लगने पर कभी भी लिफ्ट का उपयोग न करें।",
                "धुआं होने पर मुंह और नाक को गीले कपड़े से ढकें।",
            ],
        },
        "landslide": {
            "actions": [
                "खड़ी ढलानों, दीवारों और कमजोर संरचनाओं से दूर रहें।",
                "असामान्य आवाज़ों, पत्थरों के गिरने या पानी के तेज बहाव पर ध्यान दें।",
            ],
            "precautions": [
                "भूस्खलन के दौरान नदी घाटियों और जल निकासी चैनलों से बचें।",
            ],
        },
        "medical": {
            "actions": [
                "मरीज को शांत और स्थिर रखें; गंभीर खतरा न होने तक घायल व्यक्ति को न हिलाएं।",
                "अधिक खून बहने वाले घावों पर साफ दबाव डालें।",
            ],
            "precautions": [
                "आपातकालीन चिकित्सा सहायता के लिए रास्ता साफ रखें।",
            ],
        },
        "general": {
            "actions": [
                "सुरक्षित आश्रय स्थल पर रहें और आपातकालीन दल के निर्देशों की प्रतीक्षा करें।",
            ],
            "precautions": [
                "आपातकालीन अपडेट के लिए संपर्क लाइनें खुली रखें।",
            ],
        },
        "dest_prefix": "{dest} की ओर सत्यापित मार्ग का पालन करें ({dist:.1f} किमी).",
        "no_dest": "कोई सुरक्षित निकासी गंतव्य वर्तमान में पुष्टि नहीं हुआ है। सुरक्षित स्थान पर रहें।",
        "route_advisory": "मार्ग सलाह: {warning}",
    },
    "ta": {
        "flood": {
            "actions": [
                "உடனடியாக மிக உயர்ந்த தளத்திற்கு அல்லது உயரமான பகுதிக்கு செல்லுங்கள்.",
                "ஓடும் வெள்ள நீரில் நடப்பதையோ அல்லது வாகனம் ஓட்டுவதையோ தவிர்க்கவும்.",
            ],
            "precautions": [
                "பாதுகாப்பாக இருந்தால் பிரதான மின் மற்றும் எரிவாயு இணைப்புகளை அணைக்கவும்.",
                "அவசர உதவி பெட்டி, மருந்துகள் மற்றும் மொபைல் போனை நீர்ப்புகா பையில் வைக்கவும்.",
            ],
        },
        "fire": {
            "actions": [
                "அருகிலுள்ள பாதுகாப்பான தரைவழி வெளியேற்றம் மூலம் உடனடியாக கட்டிடத்தை விட்டு வெளியேறுங்கள்; புகையின் கீழ் குனிந்து செல்லுங்கள்.",
                "தீ பரவுவதை மெதுவாக்க கதவுகளை மூடுங்கள்.",
            ],
            "precautions": [
                "தீ விபத்தின் போது ஒருபோதும் லிஃப்ட்களைப் பயன்படுத்த வேண்டாம்.",
                "புகை இருந்தால் ஈரமான துணியால் வாய் மற்றும் மூக்கை மூடுங்கள்.",
            ],
        },
        "landslide": {
            "actions": [
                "செங்குத்தான சரிவுகள் மற்றும் பலவீனமான சுவர்களில் இருந்து விலகி இருங்கள்.",
            ],
            "precautions": [
                "சரிவுப் பகுதிகளில் வடிகால் கால்வாய்களைத் தவிர்க்கவும்.",
            ],
        },
        "medical": {
            "actions": [
                "பாதிக்கப்பட்டவரை அமைதியாகவும் அசையாமலும் வைத்திருங்கள்; ஆபத்து இல்லாவிட்டால் காயமடைந்தவர்களை நகர்த்த வேண்டாம்.",
                "அதிக ரத்தப்போக்கு உள்ள காயங்களுக்கு சுத்தமான அழுத்தத்தைப் பயன்படுத்துங்கள்.",
            ],
            "precautions": [
                "அவசர மருத்துவ உதவி வாகனங்களுக்கு வழியை விடுங்கள்.",
            ],
        },
        "general": {
            "actions": [
                "பாதுகாப்பான இடத்தில் இருந்து மீட்புக் குழுவின் தகவலுக்காக காத்திருங்கள்.",
            ],
            "precautions": [
                "அவசர தகவல்களுக்காக தொடர்பு வழிகளை தயாராக வைத்திருங்கள்.",
            ],
        },
        "dest_prefix": "{dest} நோக்கி சரிபார்க்கப்பட்ட பாதையைப் பின்பற்றவும் ({dist:.1f} கி.மீ).",
        "no_dest": "பாதுகாப்பான வெளியேற்ற மையம் தற்போது உறுதிப்படுத்தப்படவில்லை. பாதுகாப்பான இடத்தில் இருங்கள்.",
        "route_advisory": "பாதை எச்சரிக்கை: {warning}",
    },
    "kn": {
        "flood": {
            "actions": [
                "ತಕ್ಷಣವೇ ಎತ್ತರದ ಮಹಡಿ ಅಥವಾ ಎತ್ತರದ ಸ್ಥಳಕ್ಕೆ ತೆರಳಿ.",
                "ಹರಿಯುವ ಪ್ರವಾಹದ ನೀರಿನಲ್ಲಿ ನಡೆಯುವುದು ಅಥವಾ ವಾಹನ ಚಾಲನೆ ಮಾಡುವುದನ್ನು ತಪ್ಪಿಸಿ.",
            ],
            "precautions": [
                "ಸುರಕ್ಷಿತವಾಗಿದ್ದರೆ ಮುಖ್ಯ ವಿದ್ಯುತ್ ಮತ್ತು ಗ್ಯಾಸ್ ಸಂಪರ್ಕವನ್ನು ಆಫ್ ಮಾಡಿ.",
                "ತುರ್ತು ಕಿಟ್, ಔಷಧಿಗಳು ಮತ್ತು ಮೊಬೈಲ್ ಅನ್ನು ಜಲನಿರೋಧಕ ಚೀಲದಲ್ಲಿಡಿ.",
            ],
        },
        "fire": {
            "actions": [
                "ಹತ್ತಿರದ ಸುರಕ್ಷಿತ ನಿರ್ಗಮನದ ಮೂಲಕ ತಕ್ಷಣ ಕಟ್ಟಡವನ್ನು ಖಾಲಿ ಮಾಡಿ; ಹೊಗೆಯ ಕೆಳಗೆ ಬಗ್ಗಿರಿ.",
                "ಬೆಂಕಿ ಹರಡುವುದನ್ನು ನಿಧಾನಗೊಳಿಸಲು ಬಾಗಿಲುಗಳನ್ನು ಮುಚ್ಚಿ.",
            ],
            "precautions": [
                "ಬೆಂಕಿ ಅವಘಡದ ಸಮಯದಲ್ಲಿ ಎಂದಿಗೂ ಲಿಫ್ಟ್ ಬಳಸಬೇಡಿ.",
                "ಹೊಗೆ ಇದ್ದರೆ ಒದ್ದೆಯಾದ ಬಟ್ಟೆಯಿಂದ ಬಾಯಿ ಮತ್ತು ಮೂಗನ್ನು ಮುಚ್ಚಿಕೊಳ್ಳಿ.",
            ],
        },
        "landslide": {
            "actions": ["ಕಡಿದಾದ ಇಳಿಜಾರುಗಳು ಮತ್ತು ದುರ್ಬಲ ಗೋಡೆಗಳಿಂದ ದೂರವಿರಿ."],
            "precautions": ["ನದಿಯ ಕಣಿವೆಗಳು ಮತ್ತು ತಗ್ಗು ಪ್ರದೇಶಗಳಿಂದ ದೂರವಿರಿ."],
        },
        "medical": {
            "actions": [
                "ರೋಗಿಯನ್ನು ಶಾಂತವಾಗಿ ಮತ್ತು ಬೆಚ್ಚಗಿಡಿ; ತಕ್ಷಣದ ಅಪಾಯವಿಲ್ಲದಿದ್ದರೆ ಗಾಯಾಳುಗಳನ್ನು ಚಲಿಸಬೇಡಿ.",
                "ತೀವ್ರ ರಕ್ತಸ್ರಾವವಿರುವ ಗಾಯಗಳ ಮೇಲೆ ಸ್ವಚ್ಛ ಒತ್ತಡವನ್ನು ಹಾಕಿ.",
            ],
            "precautions": ["ತುರ್ತು ವೈದ್ಯಕೀಯ ಸಿಬ್ಬಂದಿಗಾಗಿ ಮಾರ್ಗವನ್ನು ತೆರವುಗೊಳಿಸಿ."],
        },
        "general": {
            "actions": ["ಸುರಕ್ಷಿತ ಸ್ಥಳದಲ್ಲಿ ಆಶ್ರಯ ಪಡೆದು ತುರ್ತು ರಕ್ಷಣಾ ತಂಡದ ಸೂಚನೆಗಾಗಿ ಕಾಯಿರಿ."],
            "precautions": ["ತುರ್ತು ಮಾಹಿತಿಗಾಗಿ ಸಂಪರ್ಕ ಮಾರ್ಗಗಳನ್ನು ಸಿದ್ಧವಾಗಿಡಿ."],
        },
        "dest_prefix": "{dest} ಕಡೆಗೆ ಪರಿಶೀಲಿಸಿದ ಮಾರ್ಗವನ್ನು ಅನುಸರಿಸಿ ({dist:.1f} ಕಿ.ಮೀ).",
        "no_dest": "ಸುರಕ್ಷಿತ ಸ್ಥಳಾಂತರ ಕೇಂದ್ರ ಖಚಿತವಾಗಿಲ್ಲ. ಸುರಕ್ಷಿತ ಸ್ಥಳದಲ್ಲಿಯೇ ಇರಿ.",
        "route_advisory": "ಮಾರ್ಗ ಸಲಹೆ: {warning}",
    },
    "mr": {
        "flood": {
            "actions": [
                "त्वरित सर्वात वरच्या मजल्यावर किंवा उंच जागी जा.",
                "वाहत्या पुराच्या पाण्यातून चालणे किंवा वाहन चालवणे टाळा.",
            ],
            "precautions": [
                "सुरक्षित असल्यास मुख्य विद्युत आणि गॅस पुरवठा बंद करा.",
                "आपत्कालीन किट, औषधे आणि चार्ज केलेला फोन वॉटरप्रूफ बॅगमध्ये ठेवा.",
            ],
        },
        "fire": {
            "actions": [
                "जवळच्या सुरक्षित मार्गाने त्वरित इमारत रिकामी करा; धुरामध्ये वाकून चाला.",
                "आगीचा प्रसार रोखण्यासाठी मागील दरवाजे बंद करा.",
            ],
            "precautions": [
                "आग लागल्यास कधीही लिफ्टचा वापर करू नका.",
                "धूर असल्यास ओल्या कपड्याने तोंड आणि नाक झाका.",
            ],
        },
        "landslide": {
            "actions": ["उंच कडे आणि कमकुवत बांधकामांपासून दूर राहा."],
            "precautions": ["दरडी कोसळण्याच्या भागात जाणे टाळा."],
        },
        "medical": {
            "actions": [
                "रुग्णाला शांत ठेवा; थेट धोका नसल्यास जखमी व्यक्तीला हलवू नका.",
                "रक्तस्राव थांबवण्यासाठी स्वच्छ दाबाचा वापर करा.",
            ],
            "precautions": ["आपत्कालीन वैद्यकीय मदतीसाठी रस्ता मोकळा ठेवा."],
        },
        "general": {
            "actions": ["सुरक्षित ठिकाणी राहा आणि मदत पथकाच्या सूचनांचे पालन करा."],
            "precautions": ["आपत्कालीन संपर्कासाठी फोन लाईन्स मोकळ्या ठेवा."],
        },
        "dest_prefix": "{dest} कडे जाणारा सुरक्षित मार्ग वापरा ({dist:.1f} किमी).",
        "no_dest": "कोणतेही सुरक्षित ठिकाण निश्चित नाही. सुरक्षित जागेवर राहा.",
        "route_advisory": "मार्ग सल्ला: {warning}",
    },
    "bn": {
        "flood": {
            "actions": [
                "অবিলম্বে সর্বোচ্চ তলা বা উঁচু স্থানে চলে যান।",
                "প্রবাহিত বন্যার জলে হাঁটা বা গাড়ি চালানো এড়িয়ে চলুন।",
            ],
            "precautions": [
                "নিরাপদ হলে প্রধান বিদ্যুৎ এবং গ্যাস সংযোগ বন্ধ করুন।",
                "জরুরি কিট, ওষুধ এবং চার্জযুক্ত ফোন ওয়াটারপ্রুফ ব্যাগে রাখুন।",
            ],
        },
        "fire": {
            "actions": [
                "নিকটতম নিরাপদ পথ দিয়ে অবিলম্বে ভবন ত্যাগ করুন; ধোঁয়ার নিচে নিচু হয়ে থাকুন।",
                "আগুন ছড়ানো ধীর করতে পেছনের দরজা বন্ধ করুন।",
            ],
            "precautions": [
                "আগুনের সময় কখনোই লিফট ব্যবহার করবেন না।",
                "ধোঁয়া থাকলে ভেজা কাপড় দিয়ে মুখ ও নাক ঢেকে রাখুন।",
            ],
        },
        "landslide": {
            "actions": ["খাড়া ঢাল ও দুর্বল প্রাচীর থেকে দূরে থাকুন।"],
            "precautions": ["নিচু উপত্যকা ও নর্দমা থেকে দূরে থাকুন।"],
        },
        "medical": {
            "actions": [
                "রোগীকে শান্ত ও স্থির রাখুন; সরাসরি বিপদ না থাকলে আহত ব্যক্তিকে স্থানান্তর করবেন না।",
                "রক্তপাত বন্ধ করতে পরিষ্কার চাপ প্রয়োগ করুন।",
            ],
            "precautions": ["জরুরি চিকিৎসা কর্মীদের জন্য পথ পরিষ্কার রাখুন।"],
        },
        "general": {
            "actions": ["নিরাপদ আশ্রয়ে থাকুন এবং উদ্ধারকারী দলের জন্য অপেক্ষা করুন।"],
            "precautions": ["জরুরি আপডেটের জন্য যোগাযোগের মাধ্যম প্রস্তুত রাখুন।"],
        },
        "dest_prefix": "{dest}-এর দিকে যাচাইকৃত পথ অনুসরণ করুন ({dist:.1f} কিমি)।",
        "no_dest": "কোনো নিরাপদ গন্তব্য নিশ্চিত হয়নি। নিরাপদ স্থানে থাকুন।",
        "route_advisory": "পথ নির্দেশনা: {warning}",
    },
    "gu": {
        "flood": {
            "actions": [
                "તરત જ સૌથી ઊંચા માળે અથવા ઊંચા સ્થળે પહોંચો.",
                "વહેતા પૂરના પાણીમાં ચાલવાનું કે વાહન ચલાવવાનું ટાળો.",
            ],
            "precautions": [
                "સલામત હોય તો મુખ્ય ઇલેક્ટ્રિકલ બ્રેકર અને ગેસ વાલ્વ બંધ કરો.",
                "ઇમરજન્સી કિટ, દવાઓ અને ચાર્જ કરેલો ફોન વોટરપ્રૂફ બેગમાં રાખો.",
            ],
        },
        "fire": {
            "actions": [
                "નજીકના સલામત નિકાસ દ્વારા તરત જ ઇમારત ખાલી કરો; ધુમાડામાં નીચા રહો.",
                "આગ ફેલાતી રોકવા માટે દરવાજા બંધ કરો.",
            ],
            "precautions": [
                "આગ સમયે ક્યારેય લિફ્ટનો ઉપયોગ કરશો નહીં.",
                "ધુમાડો હોય તો ભીના કપડાથી મોં અને નાક ઢાંકો.",
            ],
        },
        "landslide": {
            "actions": ["ઊંચા ઢોળાવો અને જોખમી દિવાલોથી દૂર રહો."],
            "precautions": ["ભૂસ્ખલનવાળા વિસ્તારોથી દૂર રહો."],
        },
        "medical": {
            "actions": [
                "દર્દીને શાંત અને સ્થિર રાખો; સીધો ભય ન હોય ત્યાં સુધી ઇજાગ્રસ્તને ખસેડશો નહીં.",
                "વધુ પડતા રક્તસ્રાવ પર સ્વચ્છ દબાણ આપો.",
            ],
            "precautions": ["ઇમરજન્સી મેડિકલ સહાય માટે રસ્તો ખુલ્લો રાખો."],
        },
        "general": {
            "actions": ["સલામત જગ્યાએ આશ્રય લો અને રાહત દળની સૂચનાઓની રાહ જુઓ."],
            "precautions": ["ઇમરજન્સી અપડેટ્સ માટે સંપર્ક લાઇન ખુલ્લી રાખો."],
        },
        "dest_prefix": "{dest} તરફ ચકાસાયેલ માર્ગને અનુસરો ({dist:.1f} કિમી).",
        "no_dest": "કોઈ સલામત આશ્રયસ્થાન ખાતરી થયેલ નથી. સલામત જગ્યાએ રહો.",
        "route_advisory": "માર્ગ સલાહ: {warning}",
    },
    "ml": {
        "flood": {
            "actions": [
                "ഉടൻ തന്നെ ഏറ്റവും ഉയർന്ന നിലയിലേക്കോ ഉയർന്ന സ്ഥലത്തേക്കോ മാറുക.",
                "ഒഴുകുന്ന വെള്ളത്തിലൂടെ നടക്കുകയോ വാഹനം ഓടിക്കുകയോ ചെയ്യരുത്.",
            ],
            "precautions": [
                "സുരക്ഷിതമാണെങ്കിൽ പ്രധാന വൈദ്യുതി, ഗ്യാസ് കണക്ഷനുകൾ ഓഫ് ചെയ്യുക.",
                "എമർജൻസി കിറ്റ്, മരുന്നുകൾ, ചാർജ് ചെയ്ത ഫോൺ എന്നിവ വാട്ടർപ്രൂഫ് ബാഗിൽ സൂക്ഷിക്കുക.",
            ],
        },
        "fire": {
            "actions": [
                "ഏറ്റവും അടുത്തുള്ള സുരക്ഷിത വഴിയിലൂടെ ഉടൻ കെട്ടിടത്തിൽ നിന്ന് പുറത്തുകടക്കുക.",
                "തീ പടരുന്നത് തടയാൻ വാതിലുകൾ അടയ്ക്കുക.",
            ],
            "precautions": [
                "തീപിടുത്തമുണ്ടാകുമ്പോൾ ഒരിക്കലും ലിഫ്റ്റ് ഉപയോഗിക്കരുത്.",
                "പുകയുണ്ടെങ്കിൽ നനഞ്ഞ തുണികൊണ്ട് വായും മൂക്കും മൂടുക.",
            ],
        },
        "landslide": {
            "actions": ["കുത്തനെയുള്ള ചരിവുകളിൽ നിന്നും ഭിത്തികളിൽ നിന്നും മാറുക."],
            "precautions": ["താഴ്ന്ന പ്രദേശങ്ങളിൽ നിന്നും ജലാശയങ്ങളിൽ നിന്നും മാറിനിൽക്കുക."],
        },
        "medical": {
            "actions": [
                "രോഗിയെ ശാന്തമായി കിടത്തുക; അടിയന്തര അപകടമില്ലെങ്കിൽ പരിക്കേറ്റവരെ മാറ്റരുത്.",
                "രക്തസ്രാവം തടയാൻ വൃത്തിയുള്ള തുണികൊണ്ട് അമർത്തിപ്പിടിക്കുക.",
            ],
            "precautions": ["ആംബുലൻസിനും ജീവനക്കാർക്കും വഴി നൽകുക."],
        },
        "general": {
            "actions": ["സുരക്ഷിതമായ സ്ഥാനത്ത് തുടർന്ന് രക്ഷാപ്രവർത്തകരുടെ നിർദ്ദേശങ്ങൾ പാലിക്കുക."],
            "precautions": ["അടിയന്തര വിവരങ്ങൾക്കായി ആശയവിനിമയ ലൈനുകൾ ലഭ്യമാക്കുക."],
        },
        "dest_prefix": "{dest} ലക്ഷ്യമാക്കി പരിശോധിച്ച പാത പിന്തുടരുക ({dist:.1f} കി.മീ).",
        "no_dest": "സുരക്ഷിത കേന്ദ്രം സ്ഥിരീകരിച്ചിട്ടില്ല. സുരക്ഷിത സ്ഥാനത്ത് തുടരുക.",
        "route_advisory": "റൂട്ട് മുന്നറിയിപ്പ്: {warning}",
    },
    "pa": {
        "flood": {
            "actions": [
                "ਤੁਰੰਤ ਸਭ ਤੋਂ ਉੱਚੀ ਮੰਜ਼ਿਲ ਜਾਂ ਉੱਚੀ ਥਾਂ 'ਤੇ ਜਾਓ।",
                "ਵਗਦੇ ਹੜ੍ਹ ਦੇ ਪਾਣੀ ਵਿੱਚ ਤੁਰਨ ਜਾਂ ਗੱਡੀ ਚਲਾਉਣ ਤੋਂ ਬਚੋ।",
            ],
            "precautions": [
                "ਜੇ ਸੁਰੱਖਿਅਤ ਹੋਵੇ ਤਾਂ ਮੁੱਖ ਬਿਜਲੀ ਅਤੇ ਗੈਸ ਬੰਦ ਕਰੋ।",
                "ਐਮਰਜੈਂਸੀ ਕਿੱਟ, ਦਵਾਈਆਂ ਅਤੇ ਚਾਰਜ ਕੀਤਾ ਫ਼ੋਨ ਵਾਟਰਪ੍ਰੂਫ਼ ਬੈਗ ਵਿੱਚ ਰੱਖੋ।",
            ],
        },
        "fire": {
            "actions": [
                "ਨੇੜਲੇ ਸੁਰੱਖਿਅਤ ਰਸਤੇ ਰਾਹੀਂ ਤੁਰੰਤ ਇਮਾਰਤ ਖਾਲੀ ਕਰੋ; ਧੂੰਏਂ ਦੇ ਹੇਠਾਂ ਝੁਕ ਕੇ ਰਹੋ।",
                "ਅੱਗ ਫੈਲਣ ਤੋਂ ਰੋਕਣ ਲਈ ਦਰਵਾਜ਼ੇ ਬੰਦ ਕਰੋ।",
            ],
            "precautions": [
                "ਅੱਗ ਦੌਰਾਨ ਕਦੇ ਵੀ ਲਿਫਟ ਦੀ ਵਰਤੋਂ ਨਾ ਕਰੋ।",
                "ਧੂੰਆਂ ਹੋਣ 'ਤੇ ਗਿੱਲੇ ਕੱਪੜੇ ਨਾਲ ਮੂੰਹ ਅਤੇ ਨੱਕ ਢੱਕੋ।",
            ],
        },
        "landslide": {
            "actions": ["ਖੜ੍ਹੀਆਂ ਢਲਾਣਾਂ ਅਤੇ ਕਮਜ਼ੋਰ ਕੰਧਾਂ ਤੋਂ ਦੂਰ ਰਹੋ।"],
            "precautions": ["ਪਹਾੜੀ ਨਾਲਿਆਂ ਅਤੇ ਨੀਵੀਆਂ ਥਾਵਾਂ ਤੋਂ ਬਚੋ।"],
        },
        "medical": {
            "actions": [
                "ਮਰੀਜ਼ ਨੂੰ ਸ਼ਾਂਤ ਰੱਖੋ; ਤੁਰੰਤ ਖ਼ਤਰਾ ਨਾ ਹੋਣ ਤੱਕ ਜ਼ਖਮੀ ਵਿਅਕਤੀ ਨੂੰ ਨਾ ਹਿਲਾਓ।",
                "ਜ਼ਿਆਦਾ ਖੂਨ ਵਹਿਣ ਵਾਲੇ ਜ਼ਖਮਾਂ 'ਤੇ ਸਾਫ਼ ਦਬਾਅ ਪਾਓ।",
            ],
            "precautions": ["ਮੈਡੀਕਲ ਟੀਮ ਲਈ ਰਸਤਾ ਖਾਲੀ ਰੱਖੋ।"],
        },
        "general": {
            "actions": ["ਸੁਰੱਖਿਅਤ ਸਥਾਨ 'ਤੇ ਰਹੋ ਅਤੇ ਬਚਾਅ ਟੀਮ ਦੀਆਂ ਹਦਾਇਤਾਂ ਦੀ ਉਡੀਕ ਕਰੋ।"],
            "precautions": ["ਅਪਡੇਟਸ ਲਈ ਸੰਪਰਕ ਲਾਈਨਾਂ ਖੁੱਲ੍ਹੀਆਂ ਰੱਖੋ।"],
        },
        "dest_prefix": "{dest} ਵੱਲ ਪ੍ਰਮਾਣਿਤ ਰਸਤੇ ਦੀ ਪਾਲਣਾ ਕਰੋ ({dist:.1f} ਕਿਲੋਮੀਟਰ)।",
        "no_dest": "ਕੋਈ ਸੁਰੱਖਿਅਤ ਕੇਂਦਰ ਫਿਲਹਾਲ ਤੈਅ ਨਹੀਂ ਹੈ। ਸੁਰੱਖਿਅਤ ਥਾਂ 'ਤੇ ਰਹੋ।",
        "route_advisory": "ਰਸਤਾ ਸਲਾਹ: {warning}",
    },
    "ur": {
        "flood": {
            "actions": [
                "فوری طور پر اونچی منزل یا محفوظ مقام پر منتقل ہو جائیں۔",
                "بہتے ہوئے سیلابی پانی میں چلنے یا گاڑی چلانے سے گریز کریں۔",
            ],
            "precautions": [
                "اگر محفوظ ہو تو مین بجلی کا سوئچ اور گیس والو بند کر دیں۔",
                "ایمرجنسی کٹ، ادویات اور موبائل فون واٹر پروف بیگ میں رکھیں۔",
            ],
        },
        "fire": {
            "actions": [
                "قریبی محفوظ راستے سے فوری عمارت خالی کریں؛ دھوئیں کے نیچے جھک کر رہیں۔",
                "آگ کے پھیلاؤ کو سست کرنے کے لیے پیچھے کے دروازے بند کر دیں۔",
            ],
            "precautions": [
                "آگ کے دوران کبھی بھی لفٹ کا استعمال نہ کریں۔",
                "دھواں ہونے کی صورت میں گیلے کپڑے سے منہ اور ناک ڈھانپیں۔",
            ],
        },
        "landslide": {
            "actions": ["ڈھلوانوں اور کمزور دیواروں سے دور رہیں۔"],
            "precautions": ["سیلابی نالوں اور نشیبی علاقوں سے بچیں۔"],
        },
        "medical": {
            "actions": [
                "مریض کو پرسکون رکھیں؛ فوری خطرہ نہ ہونے تک زخمی شخص کو مت ہلائیں۔",
                "خون کے بہاؤ کو روکنے کے لیے صاف دباؤ ڈالیں۔",
            ],
            "precautions": ["طبی عملے کے لیے راستہ صاف رکھیں۔"],
        },
        "general": {
            "actions": ["محفوظ مقام پر رہیں اور امدادی ٹیم کی ہدایات کا انتظار کریں۔"],
            "precautions": ["ہنگامی اطلاعات کے لیے رابطہ بحال رکھیں۔"],
        },
        "dest_prefix": "{dest} کی طرف تصدیق شدہ راستے پر چلیں ({dist:.1f} کلومیٹر)۔",
        "no_dest": "کوئی محفوظ پناہ گاہ فی الحال تصدیق شدہ نہیں ہے۔ محفوظ مقام پر رہیں۔",
        "route_advisory": "راستہ ایڈوائزری: {warning}",
    },
}


class SafetyGuidanceAgent:
    """
    Citizen Safety Guidance Advisory Agent.
    
    PURPOSE:
    Analyzes real citizen emergency reports, geolocation, multimodal evidence,
    and live operational facility availability to synthesize tailored civilian safety guidance.
    
    CRITICAL NON-NEGOTIABLE PRINCIPLES:
    - Purely ADVISORY for citizen life-safety.
    - NEVER dispatches responders, allocates emergency resources, or consumes inventory.
    - ZERO dummy or hardcoded facilities: queries real operational facilities via Places API, OSM, and MongoDB.
    - ZERO static dummy routes: computes real hazard-aware navigation corridors.
    - HITL Enforcement: Critical evacuation orders require Emergency Officer review.
    """

    @classmethod
    async def generate_safety_guidance(
        cls,
        report_id: str,
        db: Optional[AsyncIOMotorDatabase] = None,
        force_refresh: bool = False,
        change_reason: Optional[str] = None,
        trigger_event_id: Optional[str] = None,
    ) -> CitizenSafetyGuidance:
        """
        Generates or retrieves structured, contextual Safety Guidance for a citizen emergency report.
        """
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("MongoDB database connection is not initialized.")

        # 1. Check for existing active guidance if not force refreshing
        if not force_refresh:
            existing = await db["citizen_safety_guidance"].find_one({
                "report_id": report_id,
                "status": "ACTIVE",
            })
            if existing:
                return cls._doc_to_guidance(existing)

        # 2. Fetch authoritative citizen report document
        report_doc = await db["citizen_reports"].find_one({"report_id": report_id})
        if not report_doc:
            raise ValueError(f"Citizen report {report_id} not found.")

        # Extract coordinates
        loc_data = report_doc.get("location", {})
        origin_lat = float(loc_data.get("latitude", 0.0))
        origin_lng = float(loc_data.get("longitude", 0.0))
        emergency_type = report_doc.get("emergency_type", "Other")
        description = report_doc.get("description", "")
        situation_id = report_doc.get("situation_id")

        # Visual evidence & LLM extractions if present
        visual_evidence = report_doc.get("visual_evidence") or {}
        llm_extraction = report_doc.get("llm_extraction") or {}
        evidence_verification = report_doc.get("evidence_verification") or {}

        # 3. Assess Risk Level
        risk_level = cls._determine_risk_level(report_doc, visual_evidence)

        # 4. Deterministic Destination Intelligence: Real-Time Places + MongoDB facilities
        destination, dest_reason, nearby_alternatives = await cls._find_verified_destination(
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            emergency_type=emergency_type,
            db=db,
            description=description,
            visual_evidence=visual_evidence,
            llm_extraction=llm_extraction,
        )

        # 5. Real Routing (Google-Only Road Graph)
        route: Optional[RouteDetails] = None
        route_warnings: List[str] = []
        if destination:
            route = await RoutingService.calculate_hazard_aware_route(
                origin_lat=origin_lat,
                origin_lng=origin_lng,
                dest_lat=destination.latitude,
                dest_lng=destination.longitude,
                db=db,
            )
            route_warnings.extend(route.route_warnings)
            if route.route_status in (RouteStatus.CALCULATED, RouteStatus.RESTRICTED) and route.estimated_duration_minutes > 0:
                destination.distance_km = float(route.distance_km)
                destination.estimated_drive_minutes = float(route.estimated_duration_minutes)

        # Extract report language metadata
        report_lang = report_doc.get("language") or {"code": "en", "name": "English", "source": "DEFAULT"}
        lang_code = report_lang.get("code", "en").lower()

        # 6. Contextual Immediate Actions and Precautions (Multilingual)
        immediate_actions, precautions = cls._synthesize_contextual_actions(
            emergency_type=emergency_type,
            description=description,
            risk_level=risk_level,
            destination=destination,
            visual_evidence=visual_evidence,
            llm_extraction=llm_extraction,
            route=route,
            language_code=lang_code,
        )

        # 7. HITL Policy: Critical evacuation directives require officer approval
        requires_approval = (risk_level == SeverityLevel.CRITICAL and destination is not None)
        approval_state = (
            GuidanceApprovalState.PENDING_REVIEW if requires_approval else GuidanceApprovalState.AUTO_PUBLISHED
        )

        # Version calculation & history preservation
        prev_cursor = db["citizen_safety_guidance"].find({"report_id": report_id}).sort("version", -1)
        prev_docs = await prev_cursor.to_list(10)
        next_version = (prev_docs[0].get("version", 0) + 1) if prev_docs else 1

        if prev_docs:
            await db["citizen_safety_guidance"].update_many(
                {"report_id": report_id, "status": "ACTIVE"},
                {"$set": {"status": "SUPERSEDED"}}
            )

        guidance_id = generate_guidance_id()
        token = generate_secure_access_token()
        now_utc = datetime.now(timezone.utc)

        guidance = CitizenSafetyGuidance(
            guidance_id=guidance_id,
            secure_access_token=token,
            report_id=report_id,
            situation_id=situation_id,
            generated_at=now_utc,
            valid_until=now_utc + timedelta(hours=4),
            status="ACTIVE",
            emergency_type=str(emergency_type),
            risk_level=risk_level,
            immediate_actions=immediate_actions,
            precautions=precautions,
            recommended_destination=destination,
            destination_reason=dest_reason,
            nearby_alternatives=nearby_alternatives,
            route=route,
            route_warnings=route_warnings,
            avoid_locations=route.avoid_areas if route else [],
            confidence=0.92 if destination else 0.85,
            evidence_references=[
                f"Report #{report_id} Location: ({origin_lat:.4f}, {origin_lng:.4f})",
                f"Emergency Classification: {emergency_type}",
            ],
            requires_officer_approval=requires_approval,
            approval_state=approval_state,
            version=next_version,
            change_reason=change_reason,
            trigger_event_id=trigger_event_id,
            language=report_lang,
        )

        # Persist to MongoDB
        await db["citizen_safety_guidance"].insert_one(guidance.model_dump())

        # Update report document with guidance metadata
        await db["citizen_reports"].update_one(
            {"report_id": report_id},
            {
                "$set": {
                    "safety_guidance_id": guidance_id,
                    "safety_guidance_token": token,
                    "updated_at": now_utc,
                }
            },
        )

        # If auto-published, broadcast push notification to registered browsers
        if approval_state == GuidanceApprovalState.AUTO_PUBLISHED:
            try:
                await WebPushService.notify_citizen_guidance_update(guidance, db=db)
            except Exception as push_err:
                logger.warning(f"Web push dispatch exception for guidance {guidance_id}: {push_err}")

        return guidance

    @classmethod
    async def _find_verified_destination(
        cls,
        origin_lat: float,
        origin_lng: float,
        emergency_type: str,
        db: AsyncIOMotorDatabase,
        description: str = "",
        visual_evidence: Optional[Dict[str, Any]] = None,
        llm_extraction: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[VerifiedDestination], str, List[VerifiedDestination]]:
        """
        Discovers genuine, active operational facilities (shelters, hospitals, police, fire stations, bus transit)
        from Google Places / OSM and MongoDB collections, strictly aligned with citizen emergency need.
        Ranks candidate facilities by fastest road drive time and road safety.
        Returns: (primary_destination, reason, nearby_alternatives)
        """
        vis_ev = visual_evidence or {}
        llm_ext = llm_extraction or {}
        context_text = f"{emergency_type} {description} {vis_ev.get('hazard_type', '')} {llm_ext.get('summary', '')}".lower()

        # Determine need category
        need_category = "SHELTER"
        dest_type_primary = DestinationType.SHELTER

        if any(w in context_text for w in [
            "medical", "injury", "injured", "casualt", "bleeding", "unconscious",
            "heart", "trauma", "ambulance", "accident", "doctor", "hospital", "patient"
        ]):
            need_category = "MEDICAL"
            dest_type_primary = DestinationType.HEALTHCARE
        elif any(w in context_text for w in [
            "police", "security", "threat", "violence", "attack", "robbery", "assault",
            "crime", "riot", "missing person", "hostile", "gunshot"
        ]):
            need_category = "POLICE"
            dest_type_primary = DestinationType.POLICE
        elif any(w in context_text for w in [
            "fire", "smoke", "flame", "explosion", "burning", "gas leak"
        ]):
            need_category = "FIRE"
            dest_type_primary = DestinationType.FIRE_STATION
        elif any(w in context_text for w in [
            "bus", "transit", "evacuation bus", "train station", "metro", "transport"
        ]):
            need_category = "TRANSIT"
            dest_type_primary = DestinationType.BUS_STATION

        candidate_dests: List[VerifiedDestination] = []
        seen_coordinates: set = set()

        def _coord_key(lat: float, lng: float) -> Tuple[float, float]:
            return (round(lat, 3), round(lng, 3))

        # 1. Real-time Live Discovery via PlacesService (Google Places API New searchNearby)
        if origin_lat != 0.0 or origin_lng != 0.0:
            try:
                live_places = await PlacesService.discover_nearby_facilities(
                    lat=origin_lat,
                    lng=origin_lng,
                    need_category=need_category,
                    radius_meters=15000,
                    db=db,
                )
                for p in live_places:
                    ck = _coord_key(p["latitude"], p["longitude"])
                    if ck in seen_coordinates:
                        continue
                    seen_coordinates.add(ck)

                    p_type = p.get("destination_type", dest_type_primary)
                    if isinstance(p_type, str):
                        try:
                            p_type = DestinationType(p_type)
                        except Exception:
                            p_type = dest_type_primary

                    dist_km = p.get("distance_km", round(haversine_distance_km(origin_lat, origin_lng, p["latitude"], p["longitude"]), 2))
                    drive_min = p.get("estimated_drive_minutes") or PlacesService.estimate_drive_time_minutes(dist_km)

                    candidate_dests.append(
                        VerifiedDestination(
                            destination_id=p.get("place_id") or f"PLC-{p['latitude']:.4f}-{p['longitude']:.4f}",
                            destination_name=p["name"],
                            destination_type=p_type,
                            latitude=float(p["latitude"]),
                            longitude=float(p["longitude"]),
                            address_or_landmark=p.get("address") or "Live verified facility location",
                            distance_km=float(dist_km),
                            estimated_drive_minutes=float(drive_min),
                            rating=p.get("rating"),
                            open_now=p.get("open_now"),
                            place_id=p.get("place_id"),
                            provider=p.get("provider", "places_service"),
                            last_checked=datetime.now(timezone.utc),
                            operational_status="OPERATIONAL",
                            suitability_reason=f"Real-time verified operational {p_type.value.replace('_', ' ').lower()} ({dist_km:.1f} km, ~{int(drive_min)} min drive).",
                            contact_phone=p.get("contact_phone"),
                        )
                    )
            except Exception as e:
                logger.warning(f"Live places discovery failed: {e}")

        # 2. Local Operational Database Query (MongoDB: healthcare_facilities and resources)
        if need_category == "MEDICAL":
            hcf_cursor = db["healthcare_facilities"].find({
                "status": {"$nin": ["CLOSED", "INACTIVE", "DECOMMISSIONED", "DESTROYED"]}
            })
            async for doc in hcf_cursor:
                loc = doc.get("location", {})
                f_lat = loc.get("latitude")
                f_lng = loc.get("longitude")
                if f_lat is not None and f_lng is not None:
                    lat_f, lng_f = float(f_lat), float(f_lng)
                    ck = _coord_key(lat_f, lng_f)
                    if ck in seen_coordinates:
                        continue
                    seen_coordinates.add(ck)
                    dist = haversine_distance_km(origin_lat, origin_lng, lat_f, lng_f)
                    if dist <= 50.0:
                        drive_min = PlacesService.estimate_drive_time_minutes(dist)
                        cap = doc.get("capacity") or {}
                        tot_cap = float(cap.get("total") or doc.get("total_beds", 0.0))
                        avail_cap = float(cap.get("available") or doc.get("available_beds", tot_cap))
                        candidate_dests.append(
                            VerifiedDestination(
                                destination_id=doc.get("facility_id") or str(doc.get("_id", "HCF-001")),
                                destination_name=doc.get("name", "Verified Healthcare Facility"),
                                destination_type=DestinationType.HEALTHCARE,
                                latitude=lat_f,
                                longitude=lng_f,
                                address_or_landmark=doc.get("location", {}).get("address") or doc.get("address") or "Operational Medical Center",
                                distance_km=round(dist, 2),
                                estimated_drive_minutes=drive_min,
                                available_capacity=avail_cap if avail_cap > 0 else None,
                                total_capacity=tot_cap if tot_cap > 0 else None,
                                operational_status="OPERATIONAL",
                                provider="mongodb_healthcare_facilities",
                                last_checked=datetime.now(timezone.utc),
                                suitability_reason=f"Operational healthcare center ({dist:.1f} km, ~{int(drive_min)} min drive).",
                                contact_phone=doc.get("contact_info", {}).get("phone") or doc.get("phone"),
                            )
                        )

        # Query resources collection for matching operational physical facility destinations (e.g., shelters, police, fire, assembly points)
        if need_category in ["SHELTER", "TRANSIT", "POLICE", "FIRE"]:
            res_regex_map = {
                "POLICE": "(?i)police|law enforcement|patrol|security",
                "FIRE": "(?i)fire|fire station|brigade",
                "TRANSIT": "(?i)bus station|transit center|evacuation terminal|transport hub",
                "SHELTER": "(?i)shelter|evacuation center|assembly point|relief camp|community center",
            }
            res_regex = res_regex_map.get(need_category, "(?i)shelter|evacuation|assembly")
            res_cursor = db["resources"].find({
                "status": {"$in": [ResourceStatus.AVAILABLE.value, "AVAILABLE", "OPERATIONAL", "ACTIVE"]},
                "$or": [
                    {"resource_type": {"$regex": res_regex}},
                    {"type": {"$regex": res_regex}},
                    {"name": {"$regex": res_regex}},
                ]
            })
            async for doc in res_cursor:
                # Exclude commodity items / consumable supplies
                doc_name = str(doc.get("name", "")).lower()
                if any(w in doc_name for w in ["oxygen", "kit", "water bottle", "blanket", "food packet", "medicine", "generator", "tent supply"]):
                    continue

                loc = doc.get("location", {})
                f_lat = loc.get("latitude")
                f_lng = loc.get("longitude")
                if f_lat is not None and f_lng is not None:
                    lat_f, lng_f = float(f_lat), float(f_lng)
                    ck = _coord_key(lat_f, lng_f)
                    if ck in seen_coordinates:
                        continue
                    seen_coordinates.add(ck)
                    dist = haversine_distance_km(origin_lat, origin_lng, lat_f, lng_f)
                    if dist <= 50.0:
                        drive_min = PlacesService.estimate_drive_time_minutes(dist)
                        cap_sub = doc.get("capacity") or {}
                        tot_cap = float(cap_sub.get("total") or doc.get("quantity_total") or 0.0)
                        avail_cap = float(cap_sub.get("available") or doc.get("quantity_available") or tot_cap)
                        dtype = dest_type_primary
                        if need_category == "SHELTER":
                            r_type_raw = str(doc.get("resource_type") or doc.get("type") or "").upper()
                            dtype = DestinationType.SAFE_ASSEMBLY_AREA if "ASSEMBLY" in r_type_raw else DestinationType.SHELTER

                        candidate_dests.append(
                            VerifiedDestination(
                                destination_id=doc.get("resource_id") or str(doc.get("_id", "RES-001")),
                                destination_name=doc.get("name", f"Verified Operational {dtype.value.replace('_', ' ').title()}"),
                                destination_type=dtype,
                                latitude=lat_f,
                                longitude=lng_f,
                                address_or_landmark=doc.get("location", {}).get("address") or doc.get("address") or "Operational Emergency Site",
                                distance_km=round(dist, 2),
                                estimated_drive_minutes=drive_min,
                                available_capacity=avail_cap if avail_cap > 0 else None,
                                total_capacity=tot_cap if tot_cap > 0 else None,
                                operational_status="OPERATIONAL",
                                provider="mongodb_resources",
                                last_checked=datetime.now(timezone.utc),
                                suitability_reason=f"Operational {dtype.value.replace('_', ' ').lower()} ({dist:.1f} km, ~{int(drive_min)} min drive).",
                                contact_phone=doc.get("contact_info", {}).get("phone") or doc.get("phone_number") or doc.get("phone"),
                            )
                        )

        if not candidate_dests:
            return None, "NO_VERIFIED_DESTINATION_AVAILABLE", []

        # 3. Real Road Candidate Routing & Safe Corridor Ranking
        # Pre-sort candidate pool by initial proximity
        candidate_dests.sort(key=lambda d: (d.distance_km, d.estimated_drive_minutes or 999.0))
        top_candidates = candidate_dests[:6]

        # Calculate actual road routes for the top reachable candidate facilities
        if (origin_lat != 0.0 or origin_lng != 0.0) and db is not None:
            for cand in top_candidates:
                try:
                    cand_route = await RoutingService.calculate_hazard_aware_route(
                        origin_lat=origin_lat,
                        origin_lng=origin_lng,
                        dest_lat=cand.latitude,
                        dest_lng=cand.longitude,
                        db=db,
                    )
                    if cand_route.route_status in (RouteStatus.CALCULATED, RouteStatus.RESTRICTED) and cand_route.estimated_duration_minutes > 0:
                        cand.estimated_drive_minutes = float(cand_route.estimated_duration_minutes)
                        cand.distance_km = float(cand_route.distance_km)
                        p_name = cand.destination_name
                        restriction_note = " (access restriction warning)" if cand_route.route_status == RouteStatus.RESTRICTED else ""
                        cand.suitability_reason = (
                            f"Verified road-accessible {cand.destination_type.value.replace('_', ' ').lower()} "
                            f"({cand.distance_km:.1f} km road distance, ~{int(cand.estimated_drive_minutes)} min drive){restriction_note}."
                        )
                    elif cand_route.route_status == RouteStatus.ROUTE_UNSAFE:
                        # Road corridor is compromised by hazard/obstruction
                        cand.estimated_drive_minutes = (cand.estimated_drive_minutes or 50.0) + 1000.0
                except Exception as route_err:
                    logger.debug(f"Candidate route evaluation notice for {cand.destination_name}: {route_err}")

        # Rank candidates strictly by fastest actual road travel duration and road distance
        candidate_dests.sort(key=lambda d: (d.estimated_drive_minutes or 999.0, d.distance_km))

        primary_dest = candidate_dests[0]
        alternatives = candidate_dests[1:4]  # Up to 3 alternative nearby facilities

        dest_type_str = primary_dest.destination_type.value.replace('_', ' ').lower()
        est_drive_str = f", ~{int(primary_dest.estimated_drive_minutes)} min drive" if primary_dest.estimated_drive_minutes and primary_dest.estimated_drive_minutes < 500 else ""
        reason_str = (
            f"Fastest road-accessible verified operational {dest_type_str} "
            f"({primary_dest.distance_km:.1f} km{est_drive_str}) with confirmed road routing."
        )

        return primary_dest, reason_str, alternatives

    @classmethod
    def _determine_risk_level(cls, report_doc: Dict[str, Any], visual_evidence: Dict[str, Any]) -> SeverityLevel:
        impact = str(report_doc.get("citizen_impact_level", "")).upper()
        if impact == "CRITICAL":
            return SeverityLevel.CRITICAL
        elif impact == "HIGH":
            return SeverityLevel.HIGH

        vis_hazard = str(visual_evidence.get("hazard_type", "")).upper()
        if vis_hazard in ["STRUCTURAL_COLLAPSE", "BUILDING_COLLAPSE", "FIRE"] and visual_evidence.get("status") == "SUCCESS":
            return SeverityLevel.HIGH

        desc_lower = str(report_doc.get("description", "")).lower()
        if any(w in desc_lower for w in ["trapped", "buried", "bleeding", "unconscious", "explosion"]):
            return SeverityLevel.CRITICAL
        elif any(w in desc_lower for w in ["rising fast", "submerged", "fire spreading", "blocked"]):
            return SeverityLevel.HIGH

        return SeverityLevel.MEDIUM

    

    @classmethod
    def _synthesize_contextual_actions(
        cls,
        emergency_type: str,
        description: str,
        risk_level: SeverityLevel,
        destination: Optional[VerifiedDestination] = None,
        visual_evidence: Optional[Dict[str, Any]] = None,
        llm_extraction: Optional[Dict[str, Any]] = None,
        route: Optional[RouteDetails] = None,
        language_code: str = "en",
    ) -> Tuple[List[str], List[str]]:
        """
        Synthesizes deterministic, life-safety verified immediate actions and precautions
        in the citizen's preferred/detected language.
        """
        lang = (language_code or "en").lower().strip()
        lang_template = MULTILINGUAL_SAFETY_TEMPLATES.get(lang) or MULTILINGUAL_SAFETY_TEMPLATES.get("en")

        em_lower = f"{emergency_type} {description}".lower()
        if "flood" in em_lower or "water" in em_lower or "rain" in em_lower or "submerged" in em_lower:
            cat_key = "flood"
        elif "fire" in em_lower or "smoke" in em_lower or "flame" in em_lower or "burn" in em_lower:
            cat_key = "fire"
        elif "landslide" in em_lower or "slope" in em_lower or "collapse" in em_lower:
            cat_key = "landslide"
        elif "med" in em_lower or "injur" in em_lower or "bleeding" in em_lower or "unconscious" in em_lower or "accident" in em_lower:
            cat_key = "medical"
        else:
            cat_key = "general"

        cat_template = lang_template.get(cat_key, lang_template.get("general", {}))
        immediate_actions = list(cat_template.get("actions", []))
        precautions = list(cat_template.get("precautions", []))

        if destination:
            dest_prefix = lang_template.get("dest_prefix", "Follow verified route towards {dest} ({dist:.1f} km).")
            immediate_actions.append(
                dest_prefix.format(
                    dest=destination.destination_name,
                    dist=destination.distance_km,
                )
            )
        elif lang_template.get("no_dest"):
            immediate_actions.append(lang_template["no_dest"])

        if route and route.route_warnings:
            route_adv = lang_template.get("route_advisory", "Route Advisory: {warning}")
            for rw in route.route_warnings[:2]:
                precautions.append(route_adv.format(warning=rw))

        return immediate_actions, precautions

    @classmethod
    def localize_guidance(
        cls,
        guidance: CitizenSafetyGuidance,
        target_lang: str,
    ) -> CitizenSafetyGuidance:
        """
        Translates/localizes the advisory actions and precautions of a guidance object into the target language.
        Does not mutate database persistence; returns localized copy for client viewing.
        """
        lang = (target_lang or "en").lower().strip()
        lang_template = MULTILINGUAL_SAFETY_TEMPLATES.get(lang) or MULTILINGUAL_SAFETY_TEMPLATES.get("en")
        
        em_lower = (guidance.emergency_type or "").lower()
        if "flood" in em_lower or "water" in em_lower or "rain" in em_lower or "submerged" in em_lower:
            cat_key = "flood"
        elif "fire" in em_lower or "smoke" in em_lower or "flame" in em_lower or "burn" in em_lower:
            cat_key = "fire"
        elif "landslide" in em_lower or "slope" in em_lower or "collapse" in em_lower:
            cat_key = "landslide"
        elif "med" in em_lower or "injur" in em_lower or "bleeding" in em_lower or "accident" in em_lower:
            cat_key = "medical"
        else:
            cat_key = "general"

        cat_template = lang_template.get(cat_key, lang_template.get("general", {}))
        immediate_actions = list(cat_template.get("actions", []))
        precautions = list(cat_template.get("precautions", []))

        if guidance.recommended_destination:
            dest_prefix = lang_template.get("dest_prefix", "Follow verified route towards {dest} ({dist:.1f} km).")
            immediate_actions.append(
                dest_prefix.format(
                    dest=guidance.recommended_destination.destination_name,
                    dist=guidance.recommended_destination.distance_km,
                )
            )
        elif lang_template.get("no_dest"):
            immediate_actions.append(lang_template["no_dest"])

        if guidance.route_warnings:
            route_adv = lang_template.get("route_advisory", "Route Advisory: {warning}")
            for rw in guidance.route_warnings[:2]:
                precautions.append(route_adv.format(warning=rw))

        supported_names = {
            "en": "English", "te": "తెలుగు (Telugu)", "hi": "हिन्दी (Hindi)", "ta": "தமிழ் (Tamil)",
            "kn": "ಕನ್ನಡ (Kannada)", "mr": "मराठी (Marathi)", "bn": "বাংলা (Bengali)", "gu": "ગુજરાતી (Gujarati)",
            "ml": "മലയാളം (Malayalam)", "pa": "ਪੰਜਾਬੀ (Punjabi)", "ur": "اردو (Urdu)",
        }
        
        guidance_dict = guidance.model_dump()
        guidance_dict["immediate_actions"] = immediate_actions
        guidance_dict["precautions"] = precautions
        guidance_dict["language"] = {
            "code": lang,
            "name": supported_names.get(lang, lang.title()),
            "source": "CLIENT_OVERRIDE",
        }
        return CitizenSafetyGuidance(**guidance_dict)

    @classmethod
    async def evaluate_and_update_guidance_for_event(
        cls,
        event: Any,
        impact: Optional[Any] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> List[CitizenSafetyGuidance]:
        """
        Dynamically re-evaluates active Citizen Safety Guidance when an authentic operational event occurs.
        
        Evaluates:
        1. Destination Impact: Recommended facility closed, destroyed, or fully occupied.
        2. Route Corridor Impact: Road blocked, flood surge, or sensor hazard within spatial corridor buffer.
        3. Situation Escalation: Evolving hazard radius or severity change.
        
        Produces immutable, versioned guidance (V1 -> V2 -> V3) with auditable supersession.
        """
        if db is None:
            db = db_manager.db
        if db is None:
            return []

        updated_guidances: List[CitizenSafetyGuidance] = []
        cursor = db["citizen_safety_guidance"].find({"status": "ACTIVE"})

        now_utc = datetime.now(timezone.utc)
        event_source_type = getattr(event, "source_type", None)
        if hasattr(event_source_type, "value"):
            event_source_type_val = event_source_type.value
        else:
            event_source_type_val = str(event_source_type or "")

        event_source_id = str(getattr(event, "source_id", "") or "")
        event_new_state = getattr(event, "new_state", {}) or {}
        event_location = getattr(event, "location", None) or event_new_state.get("location") or {}
        event_lat = event_location.get("latitude")
        event_lng = event_location.get("longitude")
        event_id = str(getattr(event, "event_id", "") or f"EVT-{now_utc.timestamp()}")
        event_type_str = str(getattr(getattr(event, "event_type", ""), "value", getattr(event, "event_type", "")))

        async for doc in cursor:
            guidance = cls._doc_to_guidance(doc)
            
            # 1. Staleness check
            if guidance.valid_until and now_utc > guidance.valid_until:
                await db["citizen_safety_guidance"].update_one(
                    {"guidance_id": guidance.guidance_id},
                    {"$set": {"is_stale": True, "status": "STALE", "updated_at": now_utc}}
                )
                continue

            is_affected = False
            change_reasons: List[str] = []
            from app.models.enums import SafetyNotificationType
            notification_type = SafetyNotificationType.SAFETY_GUIDANCE_UPDATED

            # 2. Destination Suitability Impact Check
            if guidance.recommended_destination:
                dest_id = guidance.recommended_destination.destination_id
                if event_source_id and event_source_id == dest_id:
                    new_status = str(event_new_state.get("status", "")).upper()
                    new_avail = event_new_state.get("quantity_available") or event_new_state.get("capacity", {}).get("available")
                    if new_status in ["UNAVAILABLE", "CLOSED", "DAMAGED", "OFFLINE"] or (new_avail is not None and float(new_avail) <= 0):
                        is_affected = True
                        notification_type = SafetyNotificationType.DESTINATION_UPDATED
                        change_reasons.append(f"Designated facility ({guidance.recommended_destination.destination_name}) status changed ({new_status or 'Capacity Full'}).")

            # 3. Spatial Route Corridor & Hazard Proximity Check
            if event_lat is not None and event_lng is not None and guidance.route:
                e_lat = float(event_lat)
                e_lng = float(event_lng)
                
                dist_to_origin = haversine_distance_km(guidance.route.origin_latitude, guidance.route.origin_longitude, e_lat, e_lng)
                dist_to_dest = haversine_distance_km(guidance.route.destination_latitude, guidance.route.destination_longitude, e_lat, e_lng)
                
                min_corridor_dist = min(
                    [haversine_distance_km(pt[0], pt[1], e_lat, e_lng) for pt in guidance.route.polyline_points]
                ) if guidance.route.polyline_points else min(dist_to_origin, dist_to_dest)

                # Buffer: event within 1.2km of route waypoints or near endpoints
                if min_corridor_dist <= 1.2 or dist_to_origin <= 1.0 or dist_to_dest <= 0.8:
                    is_affected = True
                    if "ROAD_BLOCK" in event_type_str or "BLOCKED" in str(event_new_state.get("status", "")).upper():
                        notification_type = SafetyNotificationType.ROUTE_UPDATED
                        change_reasons.append(f"Transit corridor compromised by road blockage ({min_corridor_dist:.1f} km away).")
                    elif "FLOOD" in event_type_str or "FIRE" in event_type_str or "SURGE" in event_type_str or "LANDSLIDE" in event_type_str:
                        notification_type = SafetyNotificationType.HAZARD_WARNING
                        change_reasons.append(f"Hazard activity ({event_type_str}) detected near transit path ({min_corridor_dist:.1f} km).")
                    else:
                        notification_type = SafetyNotificationType.ROUTE_UPDATED
                        change_reasons.append(f"Operational change {event_type_str} detected along navigation path.")

            # 4. Situation Correlation Check
            if guidance.situation_id and getattr(event, "situation_id", None) == guidance.situation_id:
                if "SEVERITY" in event_type_str or "ESCALAT" in event_type_str or "EXPAND" in event_type_str:
                    is_affected = True
                    notification_type = SafetyNotificationType.SAFETY_GUIDANCE_UPDATED
                    change_reasons.append("Correlated emergency situation severity or impact zone has expanded.")

            if not is_affected:
                continue

            # 5. Dynamic Re-evaluation of Destination & Route
            origin_lat = guidance.route.origin_latitude if guidance.route else 0.0
            origin_lng = guidance.route.origin_longitude if guidance.route else 0.0
            
            if origin_lat == 0.0 or origin_lng == 0.0:
                rep = await db["citizen_reports"].find_one({"report_id": guidance.report_id})
                if rep:
                    loc = rep.get("location", {})
                    origin_lat = float(loc.get("latitude", 0.0))
                    origin_lng = float(loc.get("longitude", 0.0))

            new_dest, dest_reason, new_alts = await cls._find_verified_destination(
                origin_lat=origin_lat,
                origin_lng=origin_lng,
                emergency_type=guidance.emergency_type,
                db=db,
                description="; ".join(change_reasons),
            )

            new_route: Optional[RouteDetails] = None
            new_warnings: List[str] = []
            if new_dest:
                new_route = await RoutingService.calculate_hazard_aware_route(
                    origin_lat=origin_lat,
                    origin_lng=origin_lng,
                    dest_lat=new_dest.latitude,
                    dest_lng=new_dest.longitude,
                    db=db,
                )
                new_warnings.extend(new_route.route_warnings)
                if new_route.route_status == RouteStatus.ROUTE_UNSAFE:
                    notification_type = SafetyNotificationType.ROUTE_UNAVAILABLE

            fresh_actions, fresh_precautions = cls._synthesize_contextual_actions(
                emergency_type=guidance.emergency_type,
                description="; ".join(change_reasons),
                risk_level=guidance.risk_level,
                destination=new_dest,
                visual_evidence={},
                llm_extraction={},
                route=new_route,
            )

            # 6. Construct Immutable New Guidance Version
            new_version_num = guidance.version + 1
            new_guidance_id = generate_guidance_id()
            new_token = generate_secure_access_token()

            prior_history = list(guidance.history or [])
            prior_history.append({
                "guidance_id": guidance.guidance_id,
                "version": guidance.version,
                "generated_at": guidance.generated_at,
                "superseded_at": now_utc,
                "reason": "; ".join(change_reasons),
                "trigger_event_id": event_id,
            })

            requires_officer_review = bool(
                (guidance.risk_level == SeverityLevel.CRITICAL)
                or (new_route is not None and new_route.route_status == RouteStatus.ROUTE_UNSAFE)
            )
            approval_state = GuidanceApprovalState.PENDING_REVIEW if requires_officer_review else GuidanceApprovalState.AUTO_PUBLISHED

            new_guidance = CitizenSafetyGuidance(
                guidance_id=new_guidance_id,
                secure_access_token=new_token,
                report_id=guidance.report_id,
                situation_id=guidance.situation_id,
                generated_at=now_utc,
                valid_until=now_utc + timedelta(hours=4),
                status="ACTIVE",
                emergency_type=guidance.emergency_type,
                risk_level=guidance.risk_level,
                immediate_actions=fresh_actions,
                precautions=fresh_precautions,
                recommended_destination=new_dest,
                destination_reason=dest_reason,
                nearby_alternatives=new_alts,
                route=new_route,
                route_warnings=new_warnings,
                avoid_locations=new_route.avoid_areas if new_route else [],
                confidence=0.92 if new_dest else 0.85,
                evidence_references=guidance.evidence_references + [f"Dynamic Update Trigger: {event_type_str} ({event_id})"],
                requires_officer_approval=requires_officer_review,
                approval_state=approval_state,
                version=new_version_num,
                supersedes_guidance_id=guidance.guidance_id,
                superseded_by_guidance_id=None,
                trigger_event_id=event_id,
                change_reason="; ".join(change_reasons),
                is_stale=False,
                history=prior_history,
            )

            # Mark previous guidance as SUPERSEDED
            await db["citizen_safety_guidance"].update_one(
                {"guidance_id": guidance.guidance_id},
                {
                    "$set": {
                        "status": "SUPERSEDED",
                        "superseded_by_guidance_id": new_guidance_id,
                        "updated_at": now_utc,
                    }
                }
            )

            # Insert new guidance
            await db["citizen_safety_guidance"].insert_one(new_guidance.model_dump())

            # Update report pointer
            await db["citizen_reports"].update_one(
                {"report_id": guidance.report_id},
                {
                    "$set": {
                        "safety_guidance_id": new_guidance_id,
                        "safety_guidance_token": new_token,
                        "updated_at": now_utc,
                    }
                }
            )

            # If auto-published, broadcast push notification to registered devices
            if approval_state == GuidanceApprovalState.AUTO_PUBLISHED:
                try:
                    await WebPushService.notify_citizen_guidance_update(
                        new_guidance,
                        notification_type=notification_type,
                        event_id=event_id,
                        db=db,
                    )
                except Exception as push_err:
                    logger.warning(f"Push notification error on dynamic update for {new_guidance_id}: {push_err}")

            updated_guidances.append(new_guidance)
            logger.info(f"Dynamically generated Guidance {new_guidance_id} (v{new_version_num}) superseding {guidance.guidance_id} triggered by event {event_id}.")

        return updated_guidances

    @staticmethod
    def _doc_to_guidance(doc: Dict[str, Any]) -> CitizenSafetyGuidance:
        # Reconstruct verified destination if present
        dest_doc = doc.get("recommended_destination")
        dest_obj = VerifiedDestination(**dest_doc) if dest_doc else None

        # Reconstruct nearby alternatives
        nearby_alts_raw = doc.get("nearby_alternatives", [])
        nearby_alts = [VerifiedDestination(**a) for a in nearby_alts_raw if isinstance(a, dict)]

        # Reconstruct route if present
        route_doc = doc.get("route")
        route_obj = RouteDetails(**route_doc) if route_doc else None

        # Reconstruct avoid areas
        avoid_list = [HazardAvoidanceZone(**a) for a in doc.get("avoid_locations", [])]

        raw_risk = doc.get("risk_level", "MEDIUM")
        try:
            risk_enum = SeverityLevel(raw_risk)
        except Exception:
            risk_enum = SeverityLevel.MEDIUM

        raw_approval = doc.get("approval_state", "AUTO_PUBLISHED")
        try:
            approval_enum = GuidanceApprovalState(raw_approval)
        except Exception:
            approval_enum = GuidanceApprovalState.AUTO_PUBLISHED

        now_utc = datetime.now(timezone.utc)
        
        valid_until_raw = doc.get("valid_until")
        if isinstance(valid_until_raw, datetime):
            valid_until = valid_until_raw.replace(tzinfo=timezone.utc) if valid_until_raw.tzinfo is None else valid_until_raw
        else:
            valid_until = now_utc

        generated_at_raw = doc.get("generated_at")
        if isinstance(generated_at_raw, datetime):
            generated_at = generated_at_raw.replace(tzinfo=timezone.utc) if generated_at_raw.tzinfo is None else generated_at_raw
        else:
            generated_at = now_utc

        reviewed_at_raw = doc.get("reviewed_at")
        if isinstance(reviewed_at_raw, datetime):
            reviewed_at = reviewed_at_raw.replace(tzinfo=timezone.utc) if reviewed_at_raw.tzinfo is None else reviewed_at_raw
        else:
            reviewed_at = reviewed_at_raw

        is_stale_flag = bool(doc.get("is_stale", False)) or (valid_until is not None and now_utc > valid_until)

        return CitizenSafetyGuidance(
            guidance_id=doc.get("guidance_id", "GUD-UNKNOWN"),
            secure_access_token=doc.get("secure_access_token", ""),
            report_id=doc.get("report_id", ""),
            situation_id=doc.get("situation_id"),
            generated_at=generated_at,
            valid_until=valid_until,
            status=doc.get("status", "ACTIVE"),
            emergency_type=doc.get("emergency_type", "Other"),
            risk_level=risk_enum,
            immediate_actions=doc.get("immediate_actions", []),
            precautions=doc.get("precautions", []),
            recommended_destination=dest_obj,
            destination_reason=doc.get("destination_reason"),
            nearby_alternatives=nearby_alts,
            route=route_obj,
            route_warnings=doc.get("route_warnings", []),
            avoid_locations=avoid_list,
            confidence=float(doc.get("confidence", 0.90)),
            evidence_references=doc.get("evidence_references", []),
            requires_officer_approval=bool(doc.get("requires_officer_approval", False)),
            approval_state=approval_enum,
            officer_review_notes=doc.get("officer_review_notes"),
            reviewed_by=doc.get("reviewed_by"),
            reviewed_at=doc.get("reviewed_at"),
            version=int(doc.get("version", 1)),
            supersedes_guidance_id=doc.get("supersedes_guidance_id"),
            superseded_by_guidance_id=doc.get("superseded_by_guidance_id"),
            trigger_event_id=doc.get("trigger_event_id"),
            change_reason=doc.get("change_reason"),
            is_stale=is_stale_flag,
            history=doc.get("history", []),
            language=doc.get("language"),
        )
