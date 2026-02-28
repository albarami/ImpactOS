"""Generate ISIC Rev.4 division-level data files for D-2.

Produces:
    data/curated/sector_taxonomy_isic4_divisions.json
    data/curated/concordance_section_division.json
    data/curated/division_output_weights_sg_2018.json

Also updates:
    data/curated/sector_taxonomy_isic4.json  (adds division refs)

Usage:
    python -m scripts.build_division_data

Sources:
    - UN Statistics Division, ISIC Rev.4 (2008)
    - GASTAT Arabic sector names from national accounts publications
    - SG production workbook (84 active divisions verified)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "curated"

# ---------------------------------------------------------------------------
# Inactive codes in SG template (13 codes)
#   - 04,34,40,44,48,54,57,67,76,83,89: gaps/reserved in ISIC Rev.4
#   - 12: Tobacco (real ISIC, not present in Saudi economy)
#   - 92: Gambling (real ISIC, not present in Saudi economy)
# ---------------------------------------------------------------------------
INACTIVE_CODES = frozenset([
    "04", "12", "34", "40", "44", "48", "54", "57",
    "67", "76", "83", "89", "92",
])

# ---------------------------------------------------------------------------
# ISIC Rev.4 Division Data — (code, section, name_en, name_ar)
#
# Arabic names from UN ISIC Rev.4 Arabic classification and GASTAT.
# Reserved/gap codes have descriptive English name and null Arabic.
# ---------------------------------------------------------------------------
# fmt: off
DIVISIONS: list[tuple[str, str, str, str | None]] = [
    # Section A - Agriculture, forestry and fishing
    ("01", "A", "Crop and animal production, hunting and related service activities",
     "انتاج المحاصيل والانتاج الحيواني والصيد والخدمات المتصلة بها"),
    ("02", "A", "Forestry and logging",
     "الحراجة وقطع الاشجار"),
    ("03", "A", "Fishing and aquaculture",
     "صيد الاسماك وتربية الاحياء المائية"),
    ("04", "A", "(Reserved/unused in ISIC Rev.4)", None),

    # Section B - Mining and quarrying
    ("05", "B", "Mining of coal and lignite",
     "تعدين الفحم والليغنيت"),
    ("06", "B", "Extraction of crude petroleum and natural gas",
     "استخراج النفط الخام والغاز الطبيعي"),
    ("07", "B", "Mining of metal ores",
     "تعدين ركازات الفلزات"),
    ("08", "B", "Other mining and quarrying",
     "انشطة التعدين واستغلال المحاجر الاخرى"),
    ("09", "B", "Mining support service activities",
     "انشطة خدمات الدعم للتعدين"),

    # Section C - Manufacturing
    ("10", "C", "Manufacture of food products",
     "صناعة المنتجات الغذائية"),
    ("11", "C", "Manufacture of beverages",
     "صناعة المشروبات"),
    ("12", "C", "Manufacture of tobacco products",
     "صناعة منتجات التبغ"),
    ("13", "C", "Manufacture of textiles",
     "صناعة المنسوجات"),
    ("14", "C", "Manufacture of wearing apparel",
     "صناعة الملابس"),
    ("15", "C", "Manufacture of leather and related products",
     "صناعة الجلود والمنتجات ذات الصلة"),
    ("16", "C", "Manufacture of wood and of products of wood and cork, except furniture",
     "صناعة الخشب ومنتجات الخشب والفلين عدا الاثاث"),
    ("17", "C", "Manufacture of paper and paper products",
     "صناعة الورق ومنتجاته"),
    ("18", "C", "Printing and reproduction of recorded media",
     "الطباعة واستنساخ وسائط الاعلام المسجلة"),
    ("19", "C", "Manufacture of coke and refined petroleum products",
     "صناعة فحم الكوك والمنتجات النفطية المكررة"),
    ("20", "C", "Manufacture of chemicals and chemical products",
     "صناعة المواد الكيميائية والمنتجات الكيميائية"),
    ("21", "C", "Manufacture of pharmaceuticals, medicinal chemical and botanical products",
     "صناعة المستحضرات الصيدلانية والمنتجات الكيميائية الطبية والنباتية"),
    ("22", "C", "Manufacture of rubber and plastics products",
     "صناعة منتجات المطاط واللدائن"),
    ("23", "C", "Manufacture of other non-metallic mineral products",
     "صناعة المنتجات المعدنية اللافلزية الاخرى"),
    ("24", "C", "Manufacture of basic metals",
     "صناعة الفلزات القاعدية"),
    ("25", "C", "Manufacture of fabricated metal products, except machinery and equipment",
     "صناعة المنتجات المعدنية المشكلة عدا الالات والمعدات"),
    ("26", "C", "Manufacture of computer, electronic and optical products",
     "صناعة منتجات الحاسوب والالكترونيات والبصريات"),
    ("27", "C", "Manufacture of electrical equipment",
     "صناعة المعدات الكهربائية"),
    ("28", "C", "Manufacture of machinery and equipment n.e.c.",
     "صناعة الالات والمعدات غير المصنفة في موضع اخر"),
    ("29", "C", "Manufacture of motor vehicles, trailers and semi-trailers",
     "صناعة المركبات ذات المحركات والمقطورات وشبه المقطورات"),
    ("30", "C", "Manufacture of other transport equipment",
     "صناعة معدات النقل الاخرى"),
    ("31", "C", "Manufacture of furniture",
     "صناعة الاثاث"),
    ("32", "C", "Other manufacturing",
     "الصناعات التحويلية الاخرى"),
    ("33", "C", "Repair and installation of machinery and equipment",
     "اصلاح وتركيب الالات والمعدات"),
    ("34", "C", "(Reserved/unused in ISIC Rev.4)", None),

    # Section D - Electricity, gas, steam and air conditioning supply
    ("35", "D", "Electricity, gas, steam and air conditioning supply",
     "امدادات الكهرباء والغاز والبخار وتكييف الهواء"),

    # Section E - Water supply; sewerage, waste management
    ("36", "E", "Water collection, treatment and supply",
     "جمع المياه ومعالجتها وتوزيعها"),
    ("37", "E", "Sewerage",
     "الصرف الصحي"),
    ("38", "E", "Waste collection, treatment and disposal; materials recovery",
     "جمع النفايات ومعالجتها والتخلص منها واسترداد المواد"),
    ("39", "E", "Remediation activities and other waste management services",
     "انشطة المعالجة وخدمات ادارة النفايات الاخرى"),
    ("40", "E", "(Reserved/unused in ISIC Rev.4)", None),

    # Section F - Construction
    ("41", "F", "Construction of buildings",
     "تشييد المباني"),
    ("42", "F", "Civil engineering",
     "الهندسة المدنية"),
    ("43", "F", "Specialized construction activities",
     "انشطة التشييد المتخصصة"),
    ("44", "F", "(Reserved/unused in ISIC Rev.4)", None),

    # Section G - Wholesale and retail trade
    ("45", "G", "Wholesale and retail trade and repair of motor vehicles and motorcycles",
     "تجارة وصيانة واصلاح المركبات ذات المحركات والدراجات النارية"),
    ("46", "G", "Wholesale trade, except of motor vehicles and motorcycles",
     "تجارة الجملة باستثناء المركبات ذات المحركات والدراجات النارية"),
    ("47", "G", "Retail trade, except of motor vehicles and motorcycles",
     "تجارة التجزئة باستثناء المركبات ذات المحركات والدراجات النارية"),
    ("48", "G", "(Reserved/unused in ISIC Rev.4)", None),

    # Section H - Transportation and storage
    ("49", "H", "Land transport and transport via pipelines",
     "النقل البري والنقل عبر خطوط الانابيب"),
    ("50", "H", "Water transport",
     "النقل المائي"),
    ("51", "H", "Air transport",
     "النقل الجوي"),
    ("52", "H", "Warehousing and support activities for transportation",
     "التخزين وانشطة الدعم للنقل"),
    ("53", "H", "Postal and courier activities",
     "انشطة البريد والبريد السريع"),
    ("54", "H", "(Reserved/unused in ISIC Rev.4)", None),

    # Section I - Accommodation and food service activities
    ("55", "I", "Accommodation",
     "الاقامة"),
    ("56", "I", "Food and beverage service activities",
     "انشطة خدمات الطعام والمشروبات"),
    ("57", "I", "(Reserved/unused in ISIC Rev.4)", None),

    # Section J - Information and communication
    ("58", "J", "Publishing activities",
     "انشطة النشر"),
    ("59", "J", "Motion picture, video and television programme production",
     "انشطة انتاج الافلام السينمائية والفيديو والبرامج التلفزيونية"),
    ("60", "J", "Programming and broadcasting activities",
     "انشطة البرمجة والبث"),
    ("61", "J", "Telecommunications",
     "الاتصالات السلكية واللاسلكية"),
    ("62", "J", "Computer programming, consultancy and related activities",
     "برمجة الحاسوب والاستشارات والانشطة ذات الصلة"),
    ("63", "J", "Information service activities",
     "انشطة خدمات المعلومات"),

    # Section K - Financial and insurance activities
    ("64", "K", "Financial service activities, except insurance and pension funding",
     "انشطة الخدمات المالية باستثناء التامين وتمويل المعاشات التقاعدية"),
    ("65", "K", "Insurance, reinsurance and pension funding",
     "التامين واعادة التامين وتمويل المعاشات التقاعدية"),
    ("66", "K", "Activities auxiliary to financial service and insurance activities",
     "الانشطة المساعدة للخدمات المالية وانشطة التامين"),
    ("67", "K", "(Reserved/unused in ISIC Rev.4)", None),

    # Section L - Real estate activities
    ("68", "L", "Real estate activities",
     "الانشطة العقارية"),

    # Section M - Professional, scientific and technical activities
    ("69", "M", "Legal and accounting activities",
     "الانشطة القانونية وانشطة المحاسبة"),
    ("70", "M", "Activities of head offices; management consultancy activities",
     "انشطة المقار الرئيسية والانشطة الاستشارية في مجال الادارة"),
    ("71", "M", "Architectural and engineering activities; technical testing and analysis",
     "الانشطة المعمارية والهندسية والاختبارات والتحليلات التقنية"),
    ("72", "M", "Scientific research and development",
     "البحث العلمي والتطوير"),
    ("73", "M", "Advertising and market research",
     "الاعلان وبحوث السوق"),
    ("74", "M", "Other professional, scientific and technical activities",
     "الانشطة المهنية والعلمية والتقنية الاخرى"),
    ("75", "M", "Veterinary activities",
     "الانشطة البيطرية"),
    ("76", "M", "(Reserved/unused in ISIC Rev.4)", None),

    # Section N - Administrative and support service activities
    ("77", "N", "Rental and leasing activities",
     "انشطة التاجير والايجار"),
    ("78", "N", "Employment activities",
     "انشطة التوظيف"),
    ("79", "N", "Travel agency, tour operator reservation service and related activities",
     "انشطة وكالات السفر ومنظمي الرحلات وخدمات الحجز"),
    ("80", "N", "Security and investigation activities",
     "انشطة الامن والتحقيقات"),
    ("81", "N", "Services to buildings and landscape activities",
     "خدمات المباني وانشطة تنسيق المواقع"),
    ("82", "N", "Office administrative, office support and other business support activities",
     "الانشطة الادارية للمكاتب ودعم المكاتب وانشطة دعم الاعمال الاخرى"),
    ("83", "N", "(Reserved/unused in ISIC Rev.4)", None),

    # Section O - Public administration and defence
    ("84", "O", "Public administration and defence; compulsory social security",
     "الادارة العامة والدفاع والضمان الاجتماعي الالزامي"),

    # Section P - Education
    ("85", "P", "Education",
     "التعليم"),

    # Section Q - Human health and social work activities
    ("86", "Q", "Human health activities",
     "انشطة صحة الانسان"),
    ("87", "Q", "Residential care activities",
     "انشطة الرعاية السكنية"),
    ("88", "Q", "Social work activities without accommodation",
     "انشطة العمل الاجتماعي بدون اقامة"),
    ("89", "Q", "(Reserved/unused in ISIC Rev.4)", None),

    # Section R - Arts, entertainment and recreation
    ("90", "R", "Creative, arts and entertainment activities",
     "انشطة الابداع والفنون والترفيه"),
    ("91", "R", "Libraries, archives, museums and other cultural activities",
     "المكتبات والمحفوظات والمتاحف والانشطة الثقافية الاخرى"),
    ("92", "R", "Gambling and betting activities",
     "انشطة المقامرة والمراهنات"),
    ("93", "R", "Sports activities and amusement and recreation activities",
     "الانشطة الرياضية وانشطة التسلية والترفيه"),

    # Section S - Other service activities
    ("94", "S", "Activities of membership organizations",
     "انشطة منظمات العضوية"),
    ("95", "S", "Repair of computers and personal and household goods",
     "اصلاح الحواسيب والسلع الشخصية والمنزلية"),
    ("96", "S", "Other personal service activities",
     "انشطة الخدمات الشخصية الاخرى"),

    # Section T - Activities of households as employers
    ("97", "T", "Activities of households as employers of domestic personnel",
     "انشطة الاسر المعيشية بوصفها جهات موظفة لخدم المنازل"),
]
# fmt: on

# Section-level data from D-1 (for concordance and weight disaggregation)
SECTION_NAMES: dict[str, str] = {
    "A": "Agriculture, forestry and fishing",
    "B": "Mining and quarrying",
    "C": "Manufacturing",
    "D": "Electricity, gas, steam and air conditioning supply",
    "E": "Water supply; sewerage, waste management and remediation",
    "F": "Construction",
    "G": "Wholesale and retail trade; repair of motor vehicles",
    "H": "Transportation and storage",
    "I": "Accommodation and food service activities",
    "J": "Information and communication",
    "K": "Financial and insurance activities",
    "L": "Real estate activities",
    "M": "Professional, scientific and technical activities",
    "N": "Administrative and support service activities",
    "O": "Public administration and defence; compulsory social security",
    "P": "Education",
    "Q": "Human health and social work activities",
    "R": "Arts, entertainment and recreation",
    "S": "Other service activities",
    "T": "Activities of households as employers",
}

# Section-level output from D-1 model (SAR millions) for weight disaggregation
SECTION_OUTPUT_SAR_M: dict[str, float] = {
    "A": 55_000, "B": 950_000, "C": 420_000, "D": 55_000, "E": 28_000,
    "F": 280_000, "G": 260_000, "H": 170_000, "I": 65_000, "J": 95_000,
    "K": 175_000, "L": 140_000, "M": 80_000, "N": 55_000, "O": 320_000,
    "P": 130_000, "Q": 85_000, "R": 18_000, "S": 25_000, "T": 12_000,
}

# ---------------------------------------------------------------------------
# Intra-section weight distribution (how section output splits across divisions)
# These are SYNTHETIC estimates, not real GASTAT data.
# Key sectors get dominant shares based on Saudi economic structure.
# ---------------------------------------------------------------------------
DIVISION_WEIGHT_WITHIN_SECTION: dict[str, float] = {
    # A: Agriculture (01=60%, 02=5%, 03=35%)
    "01": 0.60, "02": 0.05, "03": 0.35,
    # B: Mining (05=0.5%, 06=88%, 07=1%, 08=3%, 09=7.5%)
    "05": 0.005, "06": 0.880, "07": 0.010, "08": 0.030, "09": 0.075,
    # C: Manufacturing (19=petrochem dominates)
    "10": 0.080, "11": 0.015, "13": 0.015, "14": 0.010, "15": 0.005,
    "16": 0.010, "17": 0.010, "18": 0.005, "19": 0.300, "20": 0.180,
    "21": 0.025, "22": 0.030, "23": 0.060, "24": 0.070, "25": 0.040,
    "26": 0.015, "27": 0.020, "28": 0.025, "29": 0.015, "30": 0.010,
    "31": 0.015, "32": 0.020, "33": 0.025,
    # D: Electricity/gas (single division)
    "35": 1.000,
    # E: Water/waste (36=55%, 37=10%, 38=25%, 39=10%)
    "36": 0.55, "37": 0.10, "38": 0.25, "39": 0.10,
    # F: Construction (41=50%, 42=30%, 43=20%)
    "41": 0.50, "42": 0.30, "43": 0.20,
    # G: Trade (45=15%, 46=45%, 47=40%)
    "45": 0.15, "46": 0.45, "47": 0.40,
    # H: Transport (49=45%, 50=10%, 51=20%, 52=20%, 53=5%)
    "49": 0.45, "50": 0.10, "51": 0.20, "52": 0.20, "53": 0.05,
    # I: Accommodation/food (55=35%, 56=65%)
    "55": 0.35, "56": 0.65,
    # J: ICT (58=5%, 59=5%, 60=10%, 61=50%, 62=25%, 63=5%)
    "58": 0.05, "59": 0.05, "60": 0.10, "61": 0.50, "62": 0.25, "63": 0.05,
    # K: Finance (64=60%, 65=30%, 66=10%)
    "64": 0.60, "65": 0.30, "66": 0.10,
    # L: Real estate (single division)
    "68": 1.000,
    # M: Professional (69=15%, 70=25%, 71=30%, 72=10%, 73=8%, 74=7%, 75=5%)
    "69": 0.15, "70": 0.25, "71": 0.30, "72": 0.10, "73": 0.08,
    "74": 0.07, "75": 0.05,
    # N: Admin support (77=15%, 78=25%, 79=15%, 80=20%, 81=15%, 82=10%)
    "77": 0.15, "78": 0.25, "79": 0.15, "80": 0.20, "81": 0.15, "82": 0.10,
    # O: Public admin (single division)
    "84": 1.000,
    # P: Education (single division)
    "85": 1.000,
    # Q: Health (86=70%, 87=15%, 88=15%)
    "86": 0.70, "87": 0.15, "88": 0.15,
    # R: Arts/recreation (90=25%, 91=15%, 93=60%)
    "90": 0.25, "91": 0.15, "93": 0.60,
    # S: Other services (94=30%, 95=25%, 96=45%)
    "94": 0.30, "95": 0.25, "96": 0.45,
    # T: Households (single division)
    "97": 1.000,
}


# =====================================================================
# Build functions
# =====================================================================

def _build_division_taxonomy() -> dict:
    """Build the full 97-entry division taxonomy."""
    sectors = []
    for code, section, name_en, name_ar in DIVISIONS:
        is_active = code not in INACTIVE_CODES
        sectors.append({
            "division_code": code,
            "section_code": section,
            "sector_name_en": name_en,
            "sector_name_ar": name_ar,
            "level": "division",
            "parent_section": section,
            "is_active": is_active,
            "present_in_sg_template": is_active,
        })

    active_count = sum(1 for s in sectors if s["is_active"])
    inactive_codes = sorted(s["division_code"] for s in sectors if not s["is_active"])

    return {
        "classification": "ISIC_REV4_DIVISION",
        "version": "1.0",
        "source": (
            "UN Statistics Division ISIC Rev.4 (2008) + "
            "SG production template verification"
        ),
        "code_space": "01-97",
        "total_codes": len(sectors),
        "active_count": active_count,
        "inactive_codes": inactive_codes,
        "sectors": sectors,
    }


def _build_concordance() -> dict:
    """Build section-to-division concordance (active divisions only)."""
    # Group active divisions by section
    section_divs: dict[str, list[str]] = {}
    for code, section, _en, _ar in DIVISIONS:
        if code in INACTIVE_CODES:
            continue
        section_divs.setdefault(section, []).append(code)

    mappings = []
    for section_code in sorted(SECTION_NAMES.keys()):
        divs = section_divs.get(section_code, [])
        mappings.append({
            "section_code": section_code,
            "section_name": SECTION_NAMES[section_code],
            "division_codes": sorted(divs),
        })

    return {
        "concordance_id": "isic4-section-to-division",
        "version": "1.0",
        "source": "ISIC Rev.4 standard classification hierarchy",
        "description": (
            "Maps 20 ISIC Rev.4 section codes to 84 active "
            "division codes present in SG production template"
        ),
        "mappings": mappings,
    }


def _build_division_weights() -> dict:
    """Build synthetic division-level output weights."""
    divisions = []
    for code, section, name_en, _ar in DIVISIONS:
        if code in INACTIVE_CODES:
            continue
        weight = DIVISION_WEIGHT_WITHIN_SECTION.get(code, 0.0)
        section_output = SECTION_OUTPUT_SAR_M[section]
        total_output = round(section_output * weight)
        # Convert SAR millions to SAR thousands for GASTAT compatibility
        total_output_thousands = total_output * 1000
        divisions.append({
            "code": code,
            "name": name_en,
            "section_code": section,
            "total_output": total_output_thousands,
        })

    return {
        "source": (
            "SYNTHETIC: Proportional disaggregation of D-1 section-level "
            "output using estimated intra-section weights. NOT real GASTAT data."
        ),
        "denomination": "SAR_THOUSANDS",
        "base_year": 2018,
        "is_synthetic": True,
        "total_divisions": len(divisions),
        "divisions": divisions,
    }


def _update_section_taxonomy() -> dict:
    """Update D-1 section taxonomy to add division references."""
    section_path = DATA_DIR / "sector_taxonomy_isic4.json"
    with open(section_path, encoding="utf-8") as f:
        taxonomy = json.load(f)

    # Build section -> active divisions lookup
    section_divs: dict[str, list[str]] = {}
    for code, section, _en, _ar in DIVISIONS:
        if code in INACTIVE_CODES:
            continue
        section_divs.setdefault(section, []).append(code)

    # Add divisions field to each sector
    for sector in taxonomy["sectors"]:
        code = sector["sector_code"]
        sector["divisions"] = sorted(section_divs.get(code, []))

    return taxonomy


# =====================================================================
# Validation
# =====================================================================

def _validate(taxonomy: dict, concordance: dict, weights: dict) -> bool:
    """Validate generated data for consistency."""
    ok = True

    # Check total/active counts
    total = len(taxonomy["sectors"])
    active = sum(1 for s in taxonomy["sectors"] if s["is_active"])
    if total != 97:
        print(f"ERROR: Expected 97 divisions, got {total}")
        ok = False
    if active != 84:
        print(f"ERROR: Expected 84 active, got {active}")
        ok = False

    # Check concordance covers all active divisions
    conc_divs = set()
    for m in concordance["mappings"]:
        conc_divs.update(m["division_codes"])
    if len(conc_divs) != 84:
        print(f"ERROR: Concordance covers {len(conc_divs)} divisions, expected 84")
        ok = False

    # Check weights cover all active divisions
    weight_codes = {d["code"] for d in weights["divisions"]}
    if len(weight_codes) != 84:
        print(f"ERROR: Weights cover {len(weight_codes)} divisions, expected 84")
        ok = False

    # Check concordance and weights have same codes
    if conc_divs != weight_codes:
        missing_in_weights = conc_divs - weight_codes
        missing_in_conc = weight_codes - conc_divs
        if missing_in_weights:
            print(f"ERROR: In concordance but not weights: {missing_in_weights}")
        if missing_in_conc:
            print(f"ERROR: In weights but not concordance: {missing_in_conc}")
        ok = False

    # Check within-section weights sum to ~1.0 for each section
    for section_code in SECTION_NAMES:
        section_divs_codes = [
            code for code, sec, _, _ in DIVISIONS
            if sec == section_code and code not in INACTIVE_CODES
        ]
        total_weight = sum(
            DIVISION_WEIGHT_WITHIN_SECTION.get(c, 0.0)
            for c in section_divs_codes
        )
        if abs(total_weight - 1.0) > 0.01:
            print(
                f"WARNING: Section {section_code} weights sum to "
                f"{total_weight:.4f}, expected ~1.0"
            )

    # Check no duplicate division codes
    all_codes = [s["division_code"] for s in taxonomy["sectors"]]
    if len(all_codes) != len(set(all_codes)):
        print("ERROR: Duplicate division codes found")
        ok = False

    # Check every active division has non-empty English name
    for s in taxonomy["sectors"]:
        if s["is_active"] and not s["sector_name_en"]:
            print(f"ERROR: Active division {s['division_code']} has empty name")
            ok = False

    return ok


# =====================================================================
# Main
# =====================================================================

def main() -> None:
    """Generate all D-2 data files."""
    print("Building ISIC Rev.4 division-level data files...")
    print()

    # Build
    taxonomy = _build_division_taxonomy()
    concordance = _build_concordance()
    weights = _build_division_weights()
    section_taxonomy = _update_section_taxonomy()

    # Validate
    if not _validate(taxonomy, concordance, weights):
        print("\nValidation FAILED")
        sys.exit(1)

    # Write files
    files = {
        DATA_DIR / "sector_taxonomy_isic4_divisions.json": taxonomy,
        DATA_DIR / "concordance_section_division.json": concordance,
        DATA_DIR / "division_output_weights_sg_2018.json": weights,
        DATA_DIR / "sector_taxonomy_isic4.json": section_taxonomy,
    }

    for path, data in files.items():
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Written: {path}")

    # Summary
    print()
    active_divs = [s for s in taxonomy["sectors"] if s["is_active"]]
    print(f"Division taxonomy: {len(taxonomy['sectors'])} total, "
          f"{len(active_divs)} active")
    print(f"Concordance: {len(concordance['mappings'])} sections")
    print(f"Weights: {len(weights['divisions'])} divisions")

    # Print section -> division count table
    print()
    print(f"{'Section':<8} {'Name':<50} {'Divs':>5}")
    print("-" * 65)
    for m in concordance["mappings"]:
        name = SECTION_NAMES[m["section_code"]][:48]
        print(f"{m['section_code']:<8} {name:<50} {len(m['division_codes']):>5}")

    total_mapped = sum(len(m["division_codes"]) for m in concordance["mappings"])
    print("-" * 65)
    print(f"{'TOTAL':<59} {total_mapped:>5}")
    print()
    print("BUILD COMPLETE")


if __name__ == "__main__":
    main()
