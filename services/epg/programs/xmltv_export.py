"""XMLTV export from EpgProgram database records."""

import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

from models import EpgChannel, EpgProgram
from services.epg.programs.repository import get_programs_for_channels

logger = logging.getLogger(__name__)


def format_xmltv_time(dt: datetime, offset_hours: int = 0) -> str:
    if offset_hours != 0:
        dt = dt + timedelta(hours=offset_hours)
    return dt.strftime("%Y%m%d%H%M%S +0000")


def program_to_xmltv_element(program: EpgProgram, channel_id: str, time_offset_hours: int = 0) -> ET.Element:
    prog_elem = ET.Element("programme")
    prog_elem.set("start", format_xmltv_time(program.start_time, time_offset_hours))
    prog_elem.set("stop", format_xmltv_time(program.stop_time, time_offset_hours))
    prog_elem.set("channel", channel_id)
    title_elem = ET.SubElement(prog_elem, "title")
    title_elem.set("lang", "en")
    title_elem.text = program.title
    if program.sub_title:
        sub_elem = ET.SubElement(prog_elem, "sub-title")
        sub_elem.set("lang", "en")
        sub_elem.text = program.sub_title
    if program.description:
        desc_elem = ET.SubElement(prog_elem, "desc")
        desc_elem.set("lang", "en")
        desc_elem.text = program.description
    for cat in program.get_categories_list():
        cat_elem = ET.SubElement(prog_elem, "category")
        cat_elem.set("lang", "en")
        cat_elem.text = cat
    if program.season or program.episode:
        season_part = str(program.season - 1) if program.season else ""
        episode_part = str(program.episode - 1) if program.episode else ""
        ep_num_elem = ET.SubElement(prog_elem, "episode-num")
        ep_num_elem.set("system", "xmltv_ns")
        ep_num_elem.text = f"{season_part}.{episode_part}."
        if program.season and program.episode:
            ep_num_elem2 = ET.SubElement(prog_elem, "episode-num")
            ep_num_elem2.set("system", "onscreen")
            ep_num_elem2.text = f"S{program.season:02d}E{program.episode:02d}"
    if program.episode_id:
        ep_id_elem = ET.SubElement(prog_elem, "episode-num")
        ep_id_elem.set("system", "dd_progid")
        ep_id_elem.text = program.episode_id
    if program.rating:
        rating_elem = ET.SubElement(prog_elem, "rating")
        if program.rating_system:
            rating_elem.set("system", program.rating_system)
        value_elem = ET.SubElement(rating_elem, "value")
        value_elem.text = program.rating
    if program.icon_url:
        ET.SubElement(prog_elem, "icon", src=program.icon_url)
    if program.original_air_date:
        date_elem = ET.SubElement(prog_elem, "date")
        date_elem.text = program.original_air_date.strftime("%Y%m%d")
    if program.is_new:
        ET.SubElement(prog_elem, "new")
    if program.is_premiere:
        ET.SubElement(prog_elem, "premiere")
    if program.is_live:
        ET.SubElement(prog_elem, "live")
    return prog_elem


def epg_channel_to_xmltv_element(epg_channel: EpgChannel, output_channel_id: str) -> ET.Element:
    channel_elem = ET.Element("channel")
    channel_elem.set("id", output_channel_id)
    display_name_elem = ET.SubElement(channel_elem, "display-name")
    display_name_elem.text = epg_channel.display_name or epg_channel.channel_id or output_channel_id
    if epg_channel.display_names_json:
        try:
            for name in json.loads(epg_channel.display_names_json):
                if name and name != display_name_elem.text:
                    extra_name = ET.SubElement(channel_elem, "display-name")
                    extra_name.text = name
        except (json.JSONDecodeError, TypeError) as e:
            logger.debug("Invalid display_names_json for EPG channel %s: %s", epg_channel.id, e)
    if epg_channel.icon_url:
        ET.SubElement(channel_elem, "icon", src=epg_channel.icon_url)
    return channel_elem


def generate_xmltv_from_database(
    channel_mappings: List[Tuple[int, str, int, Optional[EpgChannel]]],
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> bytes:
    if not channel_mappings:
        return b'<?xml version="1.0" encoding="UTF-8"?>\n<tv generator-info-name="iptv-proxy-v2"></tv>\n'
    root = ET.Element("tv")
    root.set("generator-info-name", "iptv-proxy-v2")
    root.set("source-info-name", "database")
    epg_channel_ids = list({cm[0] for cm in channel_mappings})
    programs_by_channel = get_programs_for_channels(epg_channel_ids, start_time, end_time)
    channel_lookup: Dict[int, List[Tuple[str, int, Optional[EpgChannel]]]] = {}
    for epg_channel_id, output_id, offset, epg_channel in channel_mappings:
        channel_lookup.setdefault(epg_channel_id, []).append((output_id, offset, epg_channel))
    added_output_ids: Set[str] = set()
    for output_mappings in channel_lookup.values():
        for output_id, offset, epg_channel in output_mappings:
            if output_id in added_output_ids:
                continue
            added_output_ids.add(output_id)
            if epg_channel:
                root.append(epg_channel_to_xmltv_element(epg_channel, output_id))
            else:
                channel_elem = ET.Element("channel")
                channel_elem.set("id", output_id)
                display_name = ET.SubElement(channel_elem, "display-name")
                display_name.text = output_id
                root.append(channel_elem)
    for epg_channel_id, programs in programs_by_channel.items():
        if not programs:
            continue
        for program in programs:
            for output_id, offset, _ in channel_lookup.get(epg_channel_id, []):
                root.append(program_to_xmltv_element(program, output_id, offset))
    return ET.tostring(root, encoding="unicode", xml_declaration=True).encode("utf-8")
