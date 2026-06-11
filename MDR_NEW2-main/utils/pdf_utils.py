"""
PDF Report Generation
Generates professional MDR risk assessment reports
"""

import os
import io
import logging
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                 TableStyle, Image, HRFlowable, KeepTogether)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import PageBreak
import uuid

logger = logging.getLogger(__name__)

# ── Color palette ──────────────────────────────────────────────────────────────
DARK_BLUE   = colors.HexColor("#1a3a5c")
MEDIUM_BLUE = colors.HexColor("#2563eb")
LIGHT_BLUE  = colors.HexColor("#dbeafe")
RED         = colors.HexColor("#dc3545")
ORANGE      = colors.HexColor("#ffc107")
GREEN       = colors.HexColor("#198754")
LIGHT_GREY  = colors.HexColor("#f8f9fa")
DARK_GREY   = colors.HexColor("#495057")
WHITE       = colors.white


def _risk_color(classification: str):
    mapping = {"High": RED, "Medium": ORANGE, "Low": GREEN}
    return mapping.get(classification, DARK_GREY)


def generate_patient_report(patient: dict, prediction: dict, contacts: list,
                             reports_folder: str,
                             patient_photo_path: str = None,
                             detected_face_path: str = None) -> str:
    """
    Generate a PDF report for a patient.
    Returns the saved file path.
    """
    os.makedirs(reports_folder, exist_ok=True)
    report_id  = str(uuid.uuid4())[:8].upper()
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename   = f"MDR_Report_{patient.get('patient_id','UNKNOWN')}_{timestamp}.pdf"
    filepath   = os.path.join(reports_folder, filename)

    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        rightMargin=1.5*cm, leftMargin=1.5*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )

    styles = getSampleStyleSheet()
    story  = []

    # ── Title block ────────────────────────────────────────────────────────────
    title_style = ParagraphStyle("Title", parent=styles["Title"],
                                  textColor=WHITE, fontSize=18, alignment=TA_CENTER)
    sub_style   = ParagraphStyle("Sub", parent=styles["Normal"],
                                  textColor=LIGHT_BLUE, fontSize=10, alignment=TA_CENTER)

    header_data = [[
        Paragraph("<b>MDR DISEASE RISK ASSESSMENT REPORT</b>", title_style),
    ]]
    header_table = Table(header_data, colWidths=[18*cm])
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), DARK_BLUE),
        ("TOPPADDING",    (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("ROUNDEDCORNERS", [4]),
    ]))
    story.append(header_table)

    # Sub-header: report meta
    meta_style = ParagraphStyle("meta", parent=styles["Normal"],
                                 fontSize=9, textColor=DARK_GREY, alignment=TA_RIGHT)
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"Report ID: <b>{report_id}</b> &nbsp;&nbsp; Generated: <b>{datetime.now().strftime('%d %b %Y, %H:%M:%S')}</b>",
        meta_style
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=MEDIUM_BLUE))
    story.append(Spacer(1, 8))

    # ── Patient photos & Info Layout ───────────────────────────────────────────
    photo_label_style = ParagraphStyle(
        "PhotoLabel",
        parent=styles["Normal"],
        fontSize=8,
        leading=9,
        textColor=DARK_BLUE,
        alignment=TA_CENTER
    )

    photo_elements = []
    if patient_photo_path and os.path.exists(patient_photo_path):
        try:
            img = Image(patient_photo_path, width=2.5*cm, height=3.0*cm)
            photo_elements.append([Paragraph("<b>Patient Photo</b>", photo_label_style), img])
        except Exception:
            pass
    if detected_face_path and os.path.exists(detected_face_path):
        try:
            img2 = Image(detected_face_path, width=2.5*cm, height=2.5*cm)
            photo_elements.append([Paragraph("<b>Detected Contact Face</b>", photo_label_style), img2])
        except Exception:
            pass

    # ── Patient information ────────────────────────────────────────────────────
    section_style = ParagraphStyle("section", parent=styles["Heading2"],
                                    textColor=DARK_BLUE, fontSize=13, spaceAfter=4)
    cell_style    = ParagraphStyle("cell", parent=styles["Normal"], fontSize=9)
    label_style   = ParagraphStyle("label", parent=styles["Normal"],
                                    fontSize=9, textColor=DARK_GREY)

    story.append(Paragraph("Patient Information", section_style))

    p = patient
    info_data = [
        ["Patient ID",    p.get("patient_id", "N/A"),      "Name",      p.get("name", "N/A")],
        ["Age / Gender",  f"{p.get('age','N/A')} / {p.get('gender','N/A')}", "Ward Type", p.get("ward_type","N/A")],
        ["Infection Type", p.get("infection_type","N/A"),  "Pathogen",  p.get("pathogen_type","N/A")],
        ["Hospital Stay", f"{p.get('length_of_hospital_stay','N/A')} days", "ICU Admitted", "Yes" if p.get("icu_admission") else "No"],
        ["Registration",  p.get("registration_date", "N/A"), "Doctor",  p.get("assigned_doctor","N/A")],
    ]

    if photo_elements:
        # Build narrower left side table to make space for photos
        info_table = Table(info_data, colWidths=[2.5*cm, 3.5*cm, 2.5*cm, 4.0*cm])
        info_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), LIGHT_BLUE),
            ("BACKGROUND", (2, 0), (2, -1), LIGHT_BLUE),
            ("FONTNAME",   (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME",   (2, 0), (2, -1), "Helvetica-Bold"),
            ("FONTSIZE",   (0, 0), (-1, -1), 9),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, LIGHT_GREY]),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))

        # Build right side photo table
        photo_rows = []
        for ph in photo_elements:
            photo_rows.append([ph[0]])  # Centered label
            photo_rows.append([ph[1]])  # Centered Image
            photo_rows.append([Spacer(1, 4)])
            
        photo_table = Table(photo_rows, colWidths=[5.5*cm])
        photo_table.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
        ]))

        # Layout info_table on left and photo_table on right
        layout_table = Table([[info_table, photo_table]], colWidths=[12.5*cm, 5.5*cm])
        layout_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (1, 0), (1, 0), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(layout_table)
    else:
        info_table = Table(info_data, colWidths=[3.5*cm, 5.5*cm, 3.5*cm, 5.5*cm])
        info_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), LIGHT_BLUE),
            ("BACKGROUND", (2, 0), (2, -1), LIGHT_BLUE),
            ("FONTNAME",   (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME",   (2, 0), (2, -1), "Helvetica-Bold"),
            ("FONTSIZE",   (0, 0), (-1, -1), 9),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, LIGHT_GREY]),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(info_table)

    story.append(Spacer(1, 12))

    # ── MDR Prediction ─────────────────────────────────────────────────────────
    story.append(Paragraph("MDR Risk Prediction (XGBoost Model)", section_style))

    risk_cls   = prediction.get("risk_classification", "Unknown")
    risk_color = _risk_color(risk_cls)

    pred_data = [
        [Paragraph("<b>Parameter</b>", label_style), Paragraph("<b>Value</b>", label_style)],
        ["MDR Probability",       f"{prediction.get('mdr_probability', 0) * 100:.1f}%"],
        ["Risk Score",            f"{prediction.get('risk_score_pct', 0):.1f} / 100"],
        ["Risk Classification",   risk_cls],
        ["Model Used",            prediction.get("model_used", "XGBoost")],
        ["Isolation Recommended", "Yes" if prediction.get("isolation_recommended") else "No"],
        ["Culture Test Required", "Yes" if prediction.get("culture_test_recommended") else "No"],
        ["Follow-up Days",        str(prediction.get("follow_up_days", 7))],
        ["Alert Level",           prediction.get("alert_level", "INFO")],
    ]

    pred_table = Table(pred_data, colWidths=[7*cm, 11*cm])
    pred_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1,  0), DARK_BLUE),
        ("TEXTCOLOR",     (0, 0), (-1,  0), WHITE),
        ("FONTNAME",      (0, 0), (-1,  0), "Helvetica-Bold"),
        ("BACKGROUND",    (0, 3), (-1,  3), risk_color),
        ("TEXTCOLOR",     (0, 3), (-1,  3), WHITE),
        ("FONTNAME",      (0, 3), (-1,  3), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(pred_table)
    story.append(Spacer(1, 12))

    # ── Top Risk Factors ───────────────────────────────────────────────────────
    top_factors = prediction.get("top_risk_factors", [])
    if top_factors:
        story.append(Paragraph("Top Risk Factors", section_style))
        tf_data = [[Paragraph("<b>Feature</b>", label_style),
                    Paragraph("<b>Importance</b>", label_style),
                    Paragraph("<b>Patient Value</b>", label_style)]]
        for f in top_factors:
            tf_data.append([f["feature"], f"{f['importance']:.4f}", str(f["value"])])

        tf_table = Table(tf_data, colWidths=[7*cm, 5.5*cm, 5.5*cm])
        tf_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), MEDIUM_BLUE),
            ("TEXTCOLOR",  (0, 0), (-1, 0), WHITE),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",   (0, 0), (-1,-1), 9),
            ("GRID",       (0, 0), (-1,-1), 0.5, colors.lightgrey),
            ("ROWBACKGROUNDS", (0, 1), (-1,-1), [WHITE, LIGHT_GREY]),
            ("TOPPADDING", (0, 0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ]))
        story.append(tf_table)
        story.append(Spacer(1, 12))

    # ── Contact Tracing ────────────────────────────────────────────────────────
    story.append(Paragraph("Contact Tracing History", section_style))
    if contacts:
        ct_data = [[Paragraph("<b>Contact With</b>", label_style),
                    Paragraph("<b>Duration (s)</b>", label_style),
                    Paragraph("<b>Exposure Score</b>", label_style),
                    Paragraph("<b>Exposure Risk</b>", label_style),
                    Paragraph("<b>Timestamp</b>", label_style)]]
        for c in contacts[:15]:
            other = c.get("person2_name") or c.get("person1_name", "Unknown")
            ct_data.append([
                other,
                f"{c.get('duration', 0):.1f}",
                f"{c.get('exposure_score', 0):.1f}",
                c.get("exposure_risk", "N/A"),
                str(c.get("start_time", ""))[:19]
            ])

        ct_table = Table(ct_data, colWidths=[4*cm, 3*cm, 3.5*cm, 3.5*cm, 4*cm])
        ct_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), DARK_BLUE),
            ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1,-1), 8),
            ("GRID",          (0, 0), (-1,-1), 0.5, colors.lightgrey),
            ("ROWBACKGROUNDS",(0, 1), (-1,-1), [WHITE, LIGHT_GREY]),
            ("TOPPADDING",    (0, 0), (-1,-1), 5),
            ("BOTTOMPADDING", (0, 0), (-1,-1), 5),
        ]))
        story.append(ct_table)
    else:
        story.append(Paragraph("No contact events recorded for this patient.", styles["Normal"]))

    story.append(Spacer(1, 12))

    # ── Final Assessment ───────────────────────────────────────────────────────
    final = prediction.get("final_assessment", {})
    if final:
        story.append(Paragraph("Final Risk Assessment", section_style))
        fc    = final.get("classification", risk_cls)
        f_col = _risk_color(fc)

        fa_data = [
            ["Final Risk Score",          f"{final.get('final_score', 0):.1f} / 100"],
            ["Final Classification",      fc],
            ["MDR Contribution",          f"{final.get('mdr_contribution', 0):.1f}"],
            ["Exposure Contribution",     f"{final.get('exposure_contribution', 0):.1f}"],
            ["Alert Level",               final.get("alert", "INFO")],
        ]
        fa_table = Table(fa_data, colWidths=[7*cm, 11*cm])
        fa_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 1), (-1, 1), f_col),
            ("TEXTCOLOR",     (0, 1), (-1, 1), WHITE),
            ("FONTNAME",      (0, 1), (-1, 1), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1,-1), 9),
            ("GRID",          (0, 0), (-1,-1), 0.5, colors.lightgrey),
            ("ROWBACKGROUNDS",(0, 0), (-1,-1), [WHITE, LIGHT_GREY]),
            ("TOPPADDING",    (0, 0), (-1,-1), 6),
            ("BOTTOMPADDING", (0, 0), (-1,-1), 6),
        ]))
        story.append(fa_table)
        story.append(Spacer(1, 12))

    # ── Clinical Recommendations ───────────────────────────────────────────────
    story.append(Paragraph("Clinical Recommendations & Alerts", section_style))
    recs = prediction.get("clinical_suggestions", [])
    if recs:
        for rec in recs:
            story.append(Paragraph(f"• {rec}", styles["Normal"]))
            story.append(Spacer(1, 3))
    else:
        story.append(Paragraph("No specific recommendations generated.", styles["Normal"]))

    # ── Footer ─────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=1, color=MEDIUM_BLUE))
    story.append(Spacer(1, 4))
    footer_style = ParagraphStyle("footer", parent=styles["Normal"],
                                   fontSize=7, textColor=DARK_GREY, alignment=TA_CENTER)
    story.append(Paragraph(
        f"MDR Surveillance System — Confidential Medical Record — Report ID: {report_id} — "
        f"Generated {datetime.now().strftime('%d %b %Y at %H:%M')}",
        footer_style
    ))

    doc.build(story)
    logger.info(f"Report generated: {filepath}")
    return filepath, filename, report_id
