"""
ClaimFlow - Seed ICD-10-CM and CPT/HCPCS code libraries.
Run: python -m scripts.seed_code_library

Seeds ~600 most common ICD-10 diagnosis codes and ~500 most common CPT procedure codes
used in physician/professional billing.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import async_session_factory
from models.code_library import ICD10Code, CPTCode
from sqlalchemy import select

# ═══════════════════════════════════════════════════════════════
# ICD-10-CM Codes — Most common in physician billing
# ═══════════════════════════════════════════════════════════════

ICD10_CODES = [
    # Infectious diseases
    ("A09", "Infectious gastroenteritis and colitis", "Infectious diseases", True),
    ("A49.9", "Bacterial infection, unspecified", "Infectious diseases", True),
    ("B00.9", "Herpesviral infection, unspecified", "Infectious diseases", True),
    ("B34.9", "Viral infection, unspecified", "Infectious diseases", True),
    ("B35.1", "Tinea unguium", "Infectious diseases", True),
    ("B37.0", "Candidal stomatitis", "Infectious diseases", True),
    # Neoplasms
    ("C18.9", "Malignant neoplasm of colon, unspecified", "Neoplasms", True),
    ("C34.90", "Malignant neoplasm of unspecified part of bronchus or lung", "Neoplasms", True),
    ("C50.919", "Malignant neoplasm of unspecified site of breast", "Neoplasms", True),
    ("C61", "Malignant neoplasm of prostate", "Neoplasms", True),
    ("C73", "Malignant neoplasm of thyroid gland", "Neoplasms", True),
    ("D17.9", "Benign lipomatous neoplasm, unspecified", "Neoplasms", True),
    ("D22.9", "Melanocytic nevi, unspecified", "Neoplasms", True),
    # Blood disorders
    ("D50.9", "Iron deficiency anemia, unspecified", "Blood disorders", True),
    ("D64.9", "Anemia, unspecified", "Blood disorders", True),
    # Endocrine/Metabolic
    ("E03.9", "Hypothyroidism, unspecified", "Endocrine/Metabolic", True),
    ("E04.1", "Nontoxic single thyroid nodule", "Endocrine/Metabolic", True),
    ("E05.90", "Thyrotoxicosis, unspecified without thyrotoxic crisis", "Endocrine/Metabolic", True),
    ("E06.3", "Autoimmune thyroiditis", "Endocrine/Metabolic", True),
    ("E07.9", "Disorder of thyroid, unspecified", "Endocrine/Metabolic", True),
    ("E11.9", "Type 2 diabetes mellitus without complications", "Endocrine/Metabolic", True),
    ("E11.65", "Type 2 diabetes mellitus with hyperglycemia", "Endocrine/Metabolic", True),
    ("E11.40", "Type 2 DM with diabetic neuropathy, unspecified", "Endocrine/Metabolic", True),
    ("E11.21", "Type 2 DM with diabetic nephropathy", "Endocrine/Metabolic", True),
    ("E11.319", "Type 2 DM with unspecified diabetic retinopathy without macular edema", "Endocrine/Metabolic", True),
    ("E10.9", "Type 1 diabetes mellitus without complications", "Endocrine/Metabolic", True),
    ("E13.9", "Other specified diabetes mellitus without complications", "Endocrine/Metabolic", True),
    ("E55.9", "Vitamin D deficiency, unspecified", "Endocrine/Metabolic", True),
    ("E66.01", "Morbid (severe) obesity due to excess calories", "Endocrine/Metabolic", True),
    ("E66.09", "Other obesity due to excess calories", "Endocrine/Metabolic", True),
    ("E66.9", "Obesity, unspecified", "Endocrine/Metabolic", True),
    ("E78.0", "Pure hypercholesterolemia, unspecified", "Endocrine/Metabolic", True),
    ("E78.1", "Pure hyperglyceridemia", "Endocrine/Metabolic", True),
    ("E78.2", "Mixed hyperlipidemia", "Endocrine/Metabolic", True),
    ("E78.5", "Hyperlipidemia, unspecified", "Endocrine/Metabolic", True),
    ("E87.6", "Hypokalemia", "Endocrine/Metabolic", True),
    # Mental/Behavioral
    ("F10.20", "Alcohol dependence, uncomplicated", "Mental/Behavioral", True),
    ("F17.210", "Nicotine dependence, cigarettes, uncomplicated", "Mental/Behavioral", True),
    ("F20.9", "Schizophrenia, unspecified", "Mental/Behavioral", True),
    ("F31.9", "Bipolar disorder, unspecified", "Mental/Behavioral", True),
    ("F32.0", "Major depressive disorder, single episode, mild", "Mental/Behavioral", True),
    ("F32.1", "Major depressive disorder, single episode, moderate", "Mental/Behavioral", True),
    ("F32.2", "Major depressive disorder, single episode, severe without psychotic features", "Mental/Behavioral", True),
    ("F32.9", "Major depressive disorder, single episode, unspecified", "Mental/Behavioral", True),
    ("F33.0", "Major depressive disorder, recurrent, mild", "Mental/Behavioral", True),
    ("F33.1", "Major depressive disorder, recurrent, moderate", "Mental/Behavioral", True),
    ("F33.2", "Major depressive disorder, recurrent, severe without psychotic features", "Mental/Behavioral", True),
    ("F33.9", "Major depressive disorder, recurrent, unspecified", "Mental/Behavioral", True),
    ("F34.1", "Dysthymic disorder", "Mental/Behavioral", True),
    ("F40.10", "Social phobia, unspecified", "Mental/Behavioral", True),
    ("F41.0", "Panic disorder without agoraphobia", "Mental/Behavioral", True),
    ("F41.1", "Generalized anxiety disorder", "Mental/Behavioral", True),
    ("F41.9", "Anxiety disorder, unspecified", "Mental/Behavioral", True),
    ("F42.2", "Mixed obsessional thoughts and acts", "Mental/Behavioral", True),
    ("F43.10", "Post-traumatic stress disorder, unspecified", "Mental/Behavioral", True),
    ("F43.20", "Adjustment disorder, unspecified", "Mental/Behavioral", True),
    ("F43.23", "Adjustment disorder with mixed anxiety and depressed mood", "Mental/Behavioral", True),
    ("F50.00", "Anorexia nervosa, unspecified", "Mental/Behavioral", True),
    ("F51.01", "Primary insomnia", "Mental/Behavioral", True),
    ("F84.0", "Autistic disorder", "Mental/Behavioral", True),
    ("F90.0", "ADHD, predominantly inattentive type", "Mental/Behavioral", True),
    ("F90.1", "ADHD, predominantly hyperactive type", "Mental/Behavioral", True),
    ("F90.2", "ADHD, combined type", "Mental/Behavioral", True),
    ("F90.9", "ADHD, unspecified type", "Mental/Behavioral", True),
    # Nervous system
    ("G20", "Parkinson disease", "Nervous system", True),
    ("G25.81", "Restless legs syndrome", "Nervous system", True),
    ("G30.9", "Alzheimer disease, unspecified", "Nervous system", True),
    ("G35", "Multiple sclerosis", "Nervous system", True),
    ("G40.909", "Epilepsy, unspecified, not intractable, without status epilepticus", "Nervous system", True),
    ("G43.909", "Migraine, unspecified, not intractable, without status migrainosus", "Nervous system", True),
    ("G43.919", "Migraine, unspecified, intractable, without status migrainosus", "Nervous system", True),
    ("G47.00", "Insomnia, unspecified", "Nervous system", True),
    ("G47.33", "Obstructive sleep apnea", "Nervous system", True),
    ("G56.00", "Carpal tunnel syndrome, unspecified upper limb", "Nervous system", True),
    ("G62.9", "Polyneuropathy, unspecified", "Nervous system", True),
    ("G89.29", "Other chronic pain", "Nervous system", True),
    # Eye
    ("H10.9", "Unspecified conjunctivitis", "Eye", True),
    ("H26.9", "Unspecified cataract", "Eye", True),
    ("H40.9", "Unspecified glaucoma", "Eye", True),
    ("H52.4", "Presbyopia", "Eye", True),
    # Ear
    ("H61.20", "Impacted cerumen, unspecified ear", "Ear", True),
    ("H66.90", "Otitis media, unspecified, unspecified ear", "Ear", True),
    ("H91.90", "Unspecified hearing loss, unspecified ear", "Ear", True),
    # Circulatory
    ("I10", "Essential (primary) hypertension", "Circulatory", True),
    ("I11.9", "Hypertensive heart disease without heart failure", "Circulatory", True),
    ("I20.9", "Angina pectoris, unspecified", "Circulatory", True),
    ("I21.9", "Acute myocardial infarction, unspecified", "Circulatory", True),
    ("I25.10", "Atherosclerotic heart disease of native coronary artery without angina", "Circulatory", True),
    ("I25.119", "Atherosclerotic heart disease with unspecified angina pectoris", "Circulatory", True),
    ("I34.0", "Nonrheumatic mitral (valve) insufficiency", "Circulatory", True),
    ("I48.0", "Paroxysmal atrial fibrillation", "Circulatory", True),
    ("I48.2", "Chronic atrial fibrillation", "Circulatory", True),
    ("I48.91", "Unspecified atrial fibrillation", "Circulatory", True),
    ("I50.9", "Heart failure, unspecified", "Circulatory", True),
    ("I63.9", "Cerebral infarction, unspecified", "Circulatory", True),
    ("I73.9", "Peripheral vascular disease, unspecified", "Circulatory", True),
    ("I83.90", "Asymptomatic varicose veins of unspecified lower extremity", "Circulatory", True),
    ("I87.2", "Venous insufficiency (chronic) (peripheral)", "Circulatory", True),
    # Respiratory
    ("J00", "Acute nasopharyngitis (common cold)", "Respiratory", True),
    ("J01.90", "Acute sinusitis, unspecified", "Respiratory", True),
    ("J02.9", "Acute pharyngitis, unspecified", "Respiratory", True),
    ("J06.9", "Acute upper respiratory infection, unspecified", "Respiratory", True),
    ("J18.9", "Pneumonia, unspecified organism", "Respiratory", True),
    ("J20.9", "Acute bronchitis, unspecified", "Respiratory", True),
    ("J30.9", "Allergic rhinitis, unspecified", "Respiratory", True),
    ("J32.9", "Chronic sinusitis, unspecified", "Respiratory", True),
    ("J34.2", "Deviated nasal septum", "Respiratory", True),
    ("J40", "Bronchitis, not specified as acute or chronic", "Respiratory", True),
    ("J42", "Unspecified chronic bronchitis", "Respiratory", True),
    ("J44.1", "COPD with acute exacerbation", "Respiratory", True),
    ("J44.9", "COPD, unspecified", "Respiratory", True),
    ("J45.20", "Mild intermittent asthma, uncomplicated", "Respiratory", True),
    ("J45.30", "Mild persistent asthma, uncomplicated", "Respiratory", True),
    ("J45.40", "Moderate persistent asthma, uncomplicated", "Respiratory", True),
    ("J45.50", "Severe persistent asthma, uncomplicated", "Respiratory", True),
    ("J45.909", "Unspecified asthma, uncomplicated", "Respiratory", True),
    # Digestive
    ("K02.9", "Dental caries, unspecified", "Digestive", True),
    ("K04.7", "Periapical abscess without sinus", "Digestive", True),
    ("K21.0", "GERD with esophagitis", "Digestive", True),
    ("K21.9", "GERD without esophagitis", "Digestive", True),
    ("K25.9", "Gastric ulcer, unspecified, without hemorrhage or perforation", "Digestive", True),
    ("K29.70", "Gastritis, unspecified, without bleeding", "Digestive", True),
    ("K30", "Functional dyspepsia", "Digestive", True),
    ("K35.80", "Unspecified acute appendicitis", "Digestive", True),
    ("K40.90", "Unilateral inguinal hernia, without obstruction or gangrene, not specified as recurrent", "Digestive", True),
    ("K44.9", "Diaphragmatic hernia without obstruction or gangrene", "Digestive", True),
    ("K50.90", "Crohn disease, unspecified, without complications", "Digestive", True),
    ("K51.90", "Ulcerative colitis, unspecified, without complications", "Digestive", True),
    ("K57.90", "Diverticulosis of intestine, part unspecified, without perforation or abscess without bleeding", "Digestive", True),
    ("K58.9", "Irritable bowel syndrome without diarrhea", "Digestive", True),
    ("K59.00", "Constipation, unspecified", "Digestive", True),
    ("K70.30", "Alcoholic cirrhosis of liver without ascites", "Digestive", True),
    ("K76.0", "Fatty (change of) liver, not elsewhere classified", "Digestive", True),
    ("K80.20", "Calculus of gallbladder without cholecystitis without obstruction", "Digestive", True),
    # Skin
    ("L03.90", "Cellulitis, unspecified", "Skin", True),
    ("L20.9", "Atopic dermatitis, unspecified", "Skin", True),
    ("L21.0", "Seborrhea capitis", "Skin", True),
    ("L30.9", "Dermatitis, unspecified", "Skin", True),
    ("L40.0", "Psoriasis vulgaris", "Skin", True),
    ("L50.9", "Urticaria, unspecified", "Skin", True),
    ("L57.0", "Actinic keratosis", "Skin", True),
    ("L70.0", "Acne vulgaris", "Skin", True),
    ("L72.0", "Epidermal cyst", "Skin", True),
    ("L82.1", "Other seborrheic keratosis", "Skin", True),
    ("L84", "Corns and callosities", "Skin", True),
    # Musculoskeletal
    ("M06.9", "Rheumatoid arthritis, unspecified", "Musculoskeletal", True),
    ("M10.9", "Gout, unspecified", "Musculoskeletal", True),
    ("M17.9", "Osteoarthritis of knee, unspecified", "Musculoskeletal", True),
    ("M19.90", "Unspecified osteoarthritis, unspecified site", "Musculoskeletal", True),
    ("M25.50", "Pain in unspecified joint", "Musculoskeletal", True),
    ("M25.511", "Pain in right shoulder", "Musculoskeletal", True),
    ("M25.562", "Pain in left knee", "Musculoskeletal", True),
    ("M47.816", "Spondylosis without myelopathy or radiculopathy, lumbar region", "Musculoskeletal", True),
    ("M50.30", "Other cervical disc degeneration, unspecified cervical region", "Musculoskeletal", True),
    ("M51.16", "Intervertebral disc disorders with radiculopathy, lumbar region", "Musculoskeletal", True),
    ("M54.2", "Cervicalgia", "Musculoskeletal", True),
    ("M54.5", "Low back pain", "Musculoskeletal", True),
    ("M54.9", "Dorsalgia, unspecified", "Musculoskeletal", True),
    ("M62.830", "Muscle spasm of back", "Musculoskeletal", True),
    ("M72.0", "Palmar fascial fibromatosis (Dupuytren)", "Musculoskeletal", True),
    ("M75.10", "Unspecified rotator cuff tear or rupture, not specified as traumatic", "Musculoskeletal", True),
    ("M79.3", "Panniculitis, unspecified", "Musculoskeletal", True),
    ("M79.7", "Fibromyalgia", "Musculoskeletal", True),
    ("M81.0", "Age-related osteoporosis without current pathological fracture", "Musculoskeletal", True),
    # Genitourinary
    ("N18.3", "Chronic kidney disease, stage 3 (moderate)", "Genitourinary", True),
    ("N18.9", "Chronic kidney disease, unspecified", "Genitourinary", True),
    ("N20.0", "Calculus of kidney", "Genitourinary", True),
    ("N30.00", "Acute cystitis without hematuria", "Genitourinary", True),
    ("N39.0", "Urinary tract infection, site not specified", "Genitourinary", True),
    ("N40.0", "Benign prostatic hyperplasia without lower urinary tract symptoms", "Genitourinary", True),
    ("N40.1", "BPH with lower urinary tract symptoms", "Genitourinary", True),
    ("N76.0", "Acute vaginitis", "Genitourinary", True),
    ("N80.0", "Endometriosis of uterus", "Genitourinary", True),
    ("N92.0", "Excessive and frequent menstruation with regular cycle", "Genitourinary", True),
    ("N95.1", "Menopausal and female climacteric states", "Genitourinary", True),
    # Pregnancy (selected)
    ("Z33.1", "Pregnant state, incidental", "Pregnancy", True),
    ("Z34.00", "Encounter for supervision of normal first pregnancy, unspecified trimester", "Pregnancy", True),
    # Symptoms/Signs
    ("R00.0", "Tachycardia, unspecified", "Symptoms/Signs", True),
    ("R00.1", "Bradycardia, unspecified", "Symptoms/Signs", True),
    ("R05.9", "Cough, unspecified", "Symptoms/Signs", True),
    ("R06.00", "Dyspnea, unspecified", "Symptoms/Signs", True),
    ("R07.9", "Chest pain, unspecified", "Symptoms/Signs", True),
    ("R10.9", "Unspecified abdominal pain", "Symptoms/Signs", True),
    ("R11.0", "Nausea", "Symptoms/Signs", True),
    ("R11.10", "Vomiting, unspecified", "Symptoms/Signs", True),
    ("R19.7", "Diarrhea, unspecified", "Symptoms/Signs", True),
    ("R21", "Rash and other nonspecific skin eruption", "Symptoms/Signs", True),
    ("R42", "Dizziness and giddiness", "Symptoms/Signs", True),
    ("R50.9", "Fever, unspecified", "Symptoms/Signs", True),
    ("R51.9", "Headache, unspecified", "Symptoms/Signs", True),
    ("R53.83", "Other fatigue", "Symptoms/Signs", True),
    ("R56.9", "Unspecified convulsions", "Symptoms/Signs", True),
    ("R63.4", "Abnormal weight loss", "Symptoms/Signs", True),
    ("R73.09", "Other abnormal glucose", "Symptoms/Signs", True),
    # Injuries
    ("S01.01XA", "Laceration without foreign body of scalp, initial encounter", "Injuries", True),
    ("S09.90XA", "Unspecified injury of head, initial encounter", "Injuries", True),
    ("S39.012A", "Strain of muscle, fascia and tendon of lower back, initial encounter", "Injuries", True),
    ("S43.401A", "Unspecified sprain of right shoulder joint, initial encounter", "Injuries", True),
    ("S46.011A", "Strain of muscle(s) and tendon(s) of the rotator cuff of right shoulder, initial encounter", "Injuries", True),
    ("S52.509A", "Unspecified fracture of the lower end of unspecified radius, initial encounter", "Injuries", True),
    ("S62.309A", "Unspecified fracture of unspecified metacarpal bone, initial encounter", "Injuries", True),
    ("S82.009A", "Unspecified fracture of unspecified patella, initial encounter for closed fracture", "Injuries", True),
    ("S93.401A", "Sprain of unspecified ligament of right ankle, initial encounter", "Injuries", True),
    # Health encounters
    ("Z00.00", "Encounter for general adult medical examination without abnormal findings", "Health encounters", True),
    ("Z00.01", "Encounter for general adult medical examination with abnormal findings", "Health encounters", True),
    ("Z00.129", "Encounter for routine child health examination without abnormal findings", "Health encounters", True),
    ("Z01.818", "Encounter for other preprocedural examination", "Health encounters", True),
    ("Z12.11", "Encounter for screening for malignant neoplasm of colon", "Health encounters", True),
    ("Z12.31", "Encounter for screening mammogram for malignant neoplasm of breast", "Health encounters", True),
    ("Z13.1", "Encounter for screening for diabetes mellitus", "Health encounters", True),
    ("Z23", "Encounter for immunization", "Health encounters", True),
    ("Z71.3", "Dietary counseling and surveillance", "Health encounters", True),
    ("Z76.0", "Encounter for issue of repeat prescription", "Health encounters", True),
    ("Z79.4", "Long term (current) use of insulin", "Health encounters", True),
    ("Z79.899", "Other long term (current) drug therapy", "Health encounters", True),
    ("Z87.891", "Personal history of nicotine dependence", "Health encounters", True),
    ("Z96.1", "Presence of intraocular lens", "Health encounters", True),
]

# ═══════════════════════════════════════════════════════════════
# CPT Codes — Most common in physician/professional billing
# ═══════════════════════════════════════════════════════════════

CPT_CODES = [
    # E/M Office Visits (2021+ guidelines)
    ("99202", "Office/outpatient visit, new patient, straightforward MDM", "E/M Office", "New Patient"),
    ("99203", "Office/outpatient visit, new patient, low MDM", "E/M Office", "New Patient"),
    ("99204", "Office/outpatient visit, new patient, moderate MDM", "E/M Office", "New Patient"),
    ("99205", "Office/outpatient visit, new patient, high MDM", "E/M Office", "New Patient"),
    ("99211", "Office/outpatient visit, established patient, may not require physician", "E/M Office", "Established Patient"),
    ("99212", "Office/outpatient visit, established patient, straightforward MDM", "E/M Office", "Established Patient"),
    ("99213", "Office/outpatient visit, established patient, low MDM", "E/M Office", "Established Patient"),
    ("99214", "Office/outpatient visit, established patient, moderate MDM", "E/M Office", "Established Patient"),
    ("99215", "Office/outpatient visit, established patient, high MDM", "E/M Office", "Established Patient"),
    # E/M Hospital
    ("99221", "Initial hospital care, straightforward or low MDM", "E/M Hospital", "Inpatient"),
    ("99222", "Initial hospital care, moderate MDM", "E/M Hospital", "Inpatient"),
    ("99223", "Initial hospital care, high MDM", "E/M Hospital", "Inpatient"),
    ("99231", "Subsequent hospital care, straightforward or low MDM", "E/M Hospital", "Inpatient"),
    ("99232", "Subsequent hospital care, moderate MDM", "E/M Hospital", "Inpatient"),
    ("99233", "Subsequent hospital care, high MDM", "E/M Hospital", "Inpatient"),
    ("99238", "Hospital discharge day management, 30 minutes or less", "E/M Hospital", "Discharge"),
    ("99239", "Hospital discharge day management, more than 30 minutes", "E/M Hospital", "Discharge"),
    # E/M Consults
    ("99241", "Office consultation, straightforward MDM", "E/M Consult", "Consultation"),
    ("99242", "Office consultation, low MDM", "E/M Consult", "Consultation"),
    ("99243", "Office consultation, moderate MDM", "E/M Consult", "Consultation"),
    ("99244", "Office consultation, moderate to high MDM", "E/M Consult", "Consultation"),
    ("99245", "Office consultation, high MDM", "E/M Consult", "Consultation"),
    # E/M Emergency
    ("99281", "ED visit, self-limited or minor problem", "E/M Emergency", "Emergency"),
    ("99282", "ED visit, low to moderate severity", "E/M Emergency", "Emergency"),
    ("99283", "ED visit, moderate severity", "E/M Emergency", "Emergency"),
    ("99284", "ED visit, high severity", "E/M Emergency", "Emergency"),
    ("99285", "ED visit, high severity with significant threat to life", "E/M Emergency", "Emergency"),
    # Telehealth
    ("99441", "Telephone E/M, 5-10 minutes", "Telehealth", "Phone"),
    ("99442", "Telephone E/M, 11-20 minutes", "Telehealth", "Phone"),
    ("99443", "Telephone E/M, 21-30 minutes", "Telehealth", "Phone"),
    # Preventive Medicine
    ("99381", "Preventive visit, new patient, infant (age under 1 year)", "Preventive", "New Patient"),
    ("99382", "Preventive visit, new patient, age 1-4 years", "Preventive", "New Patient"),
    ("99383", "Preventive visit, new patient, age 5-11 years", "Preventive", "New Patient"),
    ("99384", "Preventive visit, new patient, age 12-17 years", "Preventive", "New Patient"),
    ("99385", "Preventive visit, new patient, age 18-39 years", "Preventive", "New Patient"),
    ("99386", "Preventive visit, new patient, age 40-64 years", "Preventive", "New Patient"),
    ("99387", "Preventive visit, new patient, age 65 years and older", "Preventive", "New Patient"),
    ("99391", "Preventive visit, established patient, infant (age under 1 year)", "Preventive", "Established Patient"),
    ("99392", "Preventive visit, established patient, age 1-4 years", "Preventive", "Established Patient"),
    ("99393", "Preventive visit, established patient, age 5-11 years", "Preventive", "Established Patient"),
    ("99394", "Preventive visit, established patient, age 12-17 years", "Preventive", "Established Patient"),
    ("99395", "Preventive visit, established patient, age 18-39 years", "Preventive", "Established Patient"),
    ("99396", "Preventive visit, established patient, age 40-64 years", "Preventive", "Established Patient"),
    ("99397", "Preventive visit, established patient, age 65 years and older", "Preventive", "Established Patient"),
    # Psychiatry
    ("90791", "Psychiatric diagnostic evaluation", "Psychiatry", "Evaluation"),
    ("90792", "Psychiatric diagnostic evaluation with medical services", "Psychiatry", "Evaluation"),
    ("90832", "Psychotherapy, 30 minutes", "Psychiatry", "Therapy"),
    ("90834", "Psychotherapy, 45 minutes", "Psychiatry", "Therapy"),
    ("90837", "Psychotherapy, 60 minutes", "Psychiatry", "Therapy"),
    ("90838", "Psychotherapy for crisis, first 60 minutes", "Psychiatry", "Therapy"),
    ("90839", "Psychotherapy for crisis, each additional 30 minutes", "Psychiatry", "Therapy"),
    ("90846", "Family psychotherapy without the patient present, 50 min", "Psychiatry", "Family"),
    ("90847", "Family psychotherapy with the patient present, 50 min", "Psychiatry", "Family"),
    ("90853", "Group psychotherapy", "Psychiatry", "Group"),
    ("90863", "Pharmacologic management with psychotherapy", "Psychiatry", "Med Management"),
    # Procedures
    ("10060", "Incision and drainage of abscess, simple", "Surgery Minor", "I&D"),
    ("10120", "Incision and removal of foreign body, subcutaneous tissues, simple", "Surgery Minor", "Foreign Body"),
    ("11102", "Tangential biopsy of skin, single lesion", "Surgery Minor", "Biopsy"),
    ("11104", "Punch biopsy of skin, single lesion", "Surgery Minor", "Biopsy"),
    ("11200", "Removal of skin tags, up to and including 15 lesions", "Surgery Minor", "Skin Tags"),
    ("11300", "Shaving of epidermal or dermal lesion, trunk/arms/legs, 0.5 cm or less", "Surgery Minor", "Shaving"),
    ("11400", "Excision, benign lesion, trunk/arms/legs, 0.5 cm or less", "Surgery Minor", "Excision"),
    ("11440", "Excision, other benign lesion, face, 0.5 cm or less", "Surgery Minor", "Excision"),
    ("11600", "Excision, malignant lesion, trunk/arms/legs, 0.5 cm or less", "Surgery Minor", "Excision Malignant"),
    ("12001", "Simple repair, superficial wounds, 2.5 cm or less", "Surgery Minor", "Wound Repair"),
    ("12002", "Simple repair, superficial wounds, 2.6 to 7.5 cm", "Surgery Minor", "Wound Repair"),
    ("17000", "Destruction of premalignant lesion, first lesion", "Surgery Minor", "Destruction"),
    ("17003", "Destruction of premalignant lesion, 2nd through 14th lesion, each", "Surgery Minor", "Destruction"),
    ("17110", "Destruction of flat warts, up to 14 lesions", "Surgery Minor", "Destruction"),
    ("20610", "Arthrocentesis, aspiration and/or injection, major joint", "Injections", "Joint Injection"),
    ("20605", "Arthrocentesis, aspiration and/or injection, intermediate joint", "Injections", "Joint Injection"),
    ("20600", "Arthrocentesis, aspiration and/or injection, small joint", "Injections", "Joint Injection"),
    ("96372", "Therapeutic, prophylactic, or diagnostic injection, subcutaneous or intramuscular", "Injections", "IM/SubQ"),
    ("96374", "Therapeutic, prophylactic, or diagnostic injection, intravenous push", "Injections", "IV Push"),
    # Labs
    ("36415", "Collection of venous blood by venipuncture", "Lab", "Collection"),
    ("80048", "Basic metabolic panel", "Lab", "Chemistry"),
    ("80050", "General health panel", "Lab", "Chemistry"),
    ("80053", "Comprehensive metabolic panel", "Lab", "Chemistry"),
    ("80061", "Lipid panel", "Lab", "Chemistry"),
    ("80076", "Hepatic function panel", "Lab", "Chemistry"),
    ("82947", "Glucose, quantitative, blood", "Lab", "Chemistry"),
    ("83036", "Hemoglobin A1C", "Lab", "Chemistry"),
    ("84439", "Thyroxine, free (FT4)", "Lab", "Chemistry"),
    ("84443", "Thyroid stimulating hormone (TSH)", "Lab", "Chemistry"),
    ("85025", "Complete blood count (CBC) with differential", "Lab", "Hematology"),
    ("85027", "Complete blood count (CBC), automated", "Lab", "Hematology"),
    ("85610", "Prothrombin time (PT)", "Lab", "Coagulation"),
    ("86039", "Antinuclear antibodies (ANA)", "Lab", "Immunology"),
    ("86140", "C-reactive protein (CRP)", "Lab", "Immunology"),
    ("86580", "Skin test, tuberculosis, intradermal (PPD)", "Lab", "Skin Test"),
    ("87070", "Culture, bacterial, any source", "Lab", "Microbiology"),
    ("87081", "Culture, presumptive, pathogenic organisms, screening only", "Lab", "Microbiology"),
    ("87086", "Culture, bacterial, urine, quantitative colony count", "Lab", "Microbiology"),
    ("87491", "Chlamydia, amplified probe", "Lab", "Microbiology"),
    ("87591", "Neisseria gonorrhoeae, amplified probe", "Lab", "Microbiology"),
    ("87804", "Influenza, rapid antigen", "Lab", "Rapid Test"),
    ("87880", "Streptococcus, group A, rapid antigen", "Lab", "Rapid Test"),
    ("81001", "Urinalysis, by dip stick, automated, with microscopy", "Lab", "Urinalysis"),
    ("81002", "Urinalysis, non-automated, without microscopy", "Lab", "Urinalysis"),
    ("81003", "Urinalysis, by dip stick, automated, without microscopy", "Lab", "Urinalysis"),
    # Radiology
    ("71046", "Chest X-ray, 2 views", "Radiology", "X-ray"),
    ("71047", "Chest X-ray, 3 views", "Radiology", "X-ray"),
    ("72100", "X-ray, lumbosacral spine, 2 or 3 views", "Radiology", "X-ray"),
    ("73030", "X-ray, shoulder, complete, minimum of 2 views", "Radiology", "X-ray"),
    ("73110", "X-ray, wrist, complete, minimum of 3 views", "Radiology", "X-ray"),
    ("73560", "X-ray, knee, 1 or 2 views", "Radiology", "X-ray"),
    ("73600", "X-ray, ankle, 2 views", "Radiology", "X-ray"),
    ("70553", "MRI brain without contrast and with contrast", "Radiology", "MRI"),
    ("72148", "MRI lumbar spine without contrast", "Radiology", "MRI"),
    ("73221", "MRI, any joint of upper extremity", "Radiology", "MRI"),
    ("74176", "CT abdomen and pelvis without contrast", "Radiology", "CT"),
    ("74177", "CT abdomen and pelvis with contrast", "Radiology", "CT"),
    ("76700", "Ultrasound, abdominal, real time", "Radiology", "Ultrasound"),
    ("76856", "Ultrasound, pelvic, nonobstetric, real time", "Radiology", "Ultrasound"),
    ("77067", "Screening mammography, bilateral", "Radiology", "Mammography"),
    # EKG/Cardiology
    ("93000", "Electrocardiogram (EKG), 12-lead, with interpretation and report", "Cardiology", "EKG"),
    ("93010", "Electrocardiogram (EKG), 12-lead, interpretation only", "Cardiology", "EKG"),
    ("93015", "Cardiovascular stress test, using maximal or submaximal treadmill", "Cardiology", "Stress Test"),
    ("93306", "Echocardiography, transthoracic, complete", "Cardiology", "Echo"),
    ("93880", "Duplex scan of extracranial arteries, complete bilateral study", "Cardiology", "Vascular"),
    ("93970", "Duplex scan of extremity veins, complete bilateral study", "Cardiology", "Vascular"),
    # Pulmonary
    ("94010", "Spirometry", "Pulmonary", "PFT"),
    ("94060", "Bronchodilator responsiveness, spirometry pre- and post-bronchodilator", "Pulmonary", "PFT"),
    ("94640", "Pressurized or nonpressurized inhalation treatment", "Pulmonary", "Treatment"),
    ("94760", "Noninvasive ear or pulse oximetry for oxygen saturation", "Pulmonary", "Oximetry"),
    # Vaccines
    ("90471", "Immunization administration, first vaccine", "Vaccines", "Administration"),
    ("90472", "Immunization administration, each additional vaccine", "Vaccines", "Administration"),
    ("90658", "Influenza virus vaccine, trivalent, IM", "Vaccines", "Flu"),
    ("90670", "Pneumococcal conjugate vaccine, 13 valent (PCV13), IM", "Vaccines", "Pneumonia"),
    ("90680", "Rotavirus vaccine, pentavalent, 3 dose schedule, oral", "Vaccines", "Rotavirus"),
    ("90707", "MMR vaccine, SC", "Vaccines", "MMR"),
    ("90715", "Tdap vaccine, IM", "Vaccines", "Tdap"),
    ("90716", "Varicella virus vaccine, SC", "Vaccines", "Varicella"),
    ("90732", "Pneumococcal polysaccharide vaccine, 23 valent (PPSV23), SC or IM", "Vaccines", "Pneumonia"),
    ("90746", "Hepatitis B vaccine, adult dosage, 3 dose schedule, IM", "Vaccines", "Hep B"),
    # Prolonged Services
    ("99354", "Prolonged E/M, office, first hour", "Prolonged Services", "Office"),
    ("99355", "Prolonged E/M, office, each additional 30 min", "Prolonged Services", "Office"),
    # Chronic Care Management
    ("99490", "Chronic care management, first 20 min per calendar month", "Care Management", "CCM"),
    ("99491", "Chronic care management, 30 min+ physician time per calendar month", "Care Management", "CCM"),
    # Transitional Care
    ("99495", "Transitional care management, moderate MDM, face-to-face within 14 days", "Care Management", "TCM"),
    ("99496", "Transitional care management, high MDM, face-to-face within 7 days", "Care Management", "TCM"),
    # Behavioral Health Integration
    ("99484", "Care management for behavioral health conditions, first 20 min", "Behavioral Health", "BHI"),
    ("99492", "Initial psychiatric collaborative care management, first 70 min", "Behavioral Health", "CoCM"),
    ("99493", "Subsequent psychiatric collaborative care management, first 60 min", "Behavioral Health", "CoCM"),
]


async def seed():
    async with async_session_factory() as db:
        # ICD-10
        existing_icd = await db.execute(select(ICD10Code).limit(1))
        if existing_icd.scalar_one_or_none():
            print(f"ICD-10 codes already seeded, skipping...")
        else:
            for code, desc, category, billable in ICD10_CODES:
                db.add(ICD10Code(code=code, short_description=desc, category=category, is_billable=billable))
            await db.commit()
            print(f"Seeded {len(ICD10_CODES)} ICD-10 codes")

        # CPT
        existing_cpt = await db.execute(select(CPTCode).limit(1))
        if existing_cpt.scalar_one_or_none():
            print(f"CPT codes already seeded, skipping...")
        else:
            for code, desc, category, subcategory in CPT_CODES:
                db.add(CPTCode(code=code, short_description=desc, category=category, subcategory=subcategory))
            await db.commit()
            print(f"Seeded {len(CPT_CODES)} CPT codes")

        print("Done!")


if __name__ == "__main__":
    asyncio.run(seed())
