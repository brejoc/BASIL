from typing import Any

from flask import Flask, request, send_file
from flask_cors import CORS
from flask_restful import Resource, Api, reqparse
import json, os, sys, uuid
from html.parser import HTMLParser
from flask import jsonify
import urllib
from urllib.parse import quote
from urllib.error import HTTPError, URLError
import spdx_manager

import logging

logging.basicConfig()
logging.getLogger('sqlalchemy').setLevel(logging.ERROR)

currentdir = os.path.dirname(os.path.realpath(__file__))
db_path = os.path.join(os.path.dirname(currentdir), "db")
models_path = os.path.join(db_path, "models")
sys.path.insert(0, models_path)
sys.path.insert(0, db_path)

log_call_counter = 0

JOIN_APIS_TABLE = "apis"
JOIN_SW_REQUIREMENTS_TABLE = "sw-requirements"
JOIN_TEST_SPECIFICATIONS_TABLE = "test-specifications"

TOKEN_CHECK_OK = "TOKEN-OK"
import db_orm

from api import ApiModel, ApiHistoryModel
from api_justification import *
from api_sw_requirement import *
from api_test_case import *
from api_test_specification import *
from comment import *
from justification import *
from note import *
from sw_requirement import *
from sw_requirement_test_case import *
from sw_requirement_test_specification import *
from test_case import *
from test_specification import *
from test_specification_test_case import *

app = Flask("BASIL-API")
api = Api(app)
CORS(app)

token_parser = reqparse.RequestParser()
token_parser.add_argument('token', location="form")

_A = 'api'
_As = f'{_A}s'
_SR = 'sw_requirement'
_SRs = f'{_SR}s'
_TS = 'test_specification'
_TSs = f'{_TS}s'
_TC = 'test_case'
_TCs = f'{_TC}s'
_J = 'justification'
_Js = f'{_J}s'


def get_api_from_request(_request, _db_session):
    if 'api-id' not in _request.keys():
        return None

    query = _db_session.query(ApiModel).filter(
        ApiModel.id == _request['api-id']
    )
    apis = query.all()

    if len(apis) == 1:
        return apis[0]

    return None


def get_combined_history_object(_obj, _map, _obj_fields, _map_fields):
    _obj_fields += ['version']
    _map_fields += ['version']

    obj_version = _obj['version'] if 'version' in _obj.keys() else ''
    map_version = _map['version'] if 'version' in _map.keys() else ''

    if map_version != '':
        combined_version = f'{_obj["version"]}.{_map["version"]}'
    else:
        combined_version = f'{_obj["version"]}'

    if 'created_at' in _map.keys():
        combined_date = _obj['created_at'] if _obj['created_at'] > _map['created_at'] else _map['created_at']
    else:
        combined_date = _obj['created_at']

    _combined = {'version': combined_version,
                 'object': {},
                 'mapping': {},
                 'created_at': combined_date}

    for k in _obj_fields:
        if k in _obj.keys():
            _combined['object'][k] = _obj[k]

    for j in _map_fields:
        if j in _map.keys():
            _combined['mapping'][j] = _map[j]

    return _combined


def get_reduced_history_data(history_data, _obj_fields, _map_fields):
    """

    """
    fields_to_skip = ['version', 'created_at', 'updated_at']

    if len(history_data) == 0:
        return []

    ret = [{'version': history_data[0]['version'],
            'object': {},
            'mapping': {},
            'created_at': history_data[0]['created_at'].strftime("%d %b %y %H:%M")}]

    for k in _obj_fields:
        if k in history_data[0]['object'].keys() and k not in fields_to_skip:
            ret[0]['object'][k] = history_data[0]['object'][k]

    for j in _map_fields:
        if j in history_data[0]['mapping'].keys() and j not in fields_to_skip:
            ret[0]['mapping'][j] = history_data[0]['mapping'][j]

    if len(history_data) > 1:
        for i in range(1, len(history_data)):
            tmp = {'object': {},
                   'mapping': {},
                   'version': history_data[i]['version'],
                   'created_at': history_data[i]['created_at'].strftime("%d %b %y %H:%M")}

            last_version = history_data[i - 1]['version'].split(".")
            current_version = history_data[i]['version'].split(".")

            if last_version[0] != current_version[0]:
                # object changed
                for k in _obj_fields:
                    if k in history_data[i]['object'].keys() and k not in fields_to_skip:
                        if history_data[i]['object'][k] != history_data[i - 1]['object'][k]:
                            tmp['object'][k] = history_data[i]['object'][k]

            if len(last_version) > 1 and len(current_version) > 1:
                if last_version[1] != current_version[1]:
                    # mapping changed
                    for j in _map_fields:
                        if j in history_data[i]['mapping'].keys() and j not in fields_to_skip:
                            if history_data[i]['mapping'][j] != history_data[i - 1]['mapping'][j]:
                                tmp['mapping'][j] = history_data[i]['mapping'][j]
            ret.append(tmp)

    return ret


def get_work_item_open_html(work_item_type, title, version):
    work_item_type = work_item_type.replace("_", "-")
    work_item_desc = work_item_type.replace("-", " ").capitalize()

    tmp = ''
    # if direct == 1:
    #    tmp += '<div class="div-work-items-direct">'
    # else:
    #    tmp += f'<div name="indirect-{work_item_type}" class="div-work-items-indirect indirect-{nesting}-nesting">'
    tmp += f'<div style="border-bottom:1px solid black">'
    tmp += '<div class="div-work-item-title">'
    tmp += '<p>'
    tmp += f'<span class="meaning_version">v{version}</span>' \
           f'<span class="meaning_title" title="{work_item_desc}">{title}</span>'
    tmp += '</p>'
    tmp += '</div>'
    tmp += '<div class="div-work-item-action-buttons">'
    return tmp


def get_dict_without_keys(_dict, _undesired_keys):
    current_keys = _dict.keys()
    for k in _undesired_keys:
        if k in current_keys:
            del _dict[k]
    return _dict


def get_work_item_close_html():
    tmp = '</div>'
    tmp += '<br clear="all" />'
    tmp += '</div>'
    return tmp


def get_indirect_work_items_section_open_html(work_item_type, nesting, coverage):
    work_item_type = work_item_type.replace("_", "-")
    work_item_desc = work_item_type.replace("-", " ").capitalize()

    tmp = ''
    tmp += f'<div name="indirect-{work_item_type}" class="div-work-items-indirect indirect-{nesting}-nesting">'
    tmp += f'<span class="span-indirect-title">{work_item_desc}</span> '
    tmp += f'<progress name="coverage-progress" style="height:20px; width: 100px;" value="{coverage}" max="100" title="{coverage}"></progress>'
    return tmp


def get_api_specification(_url_or_path):
    if _url_or_path == None:
        return None
    else:
        _url_or_path = _url_or_path.strip()
        if len(_url_or_path) == 0:
            return None

        if _url_or_path.startswith("http"):
            try:
                resource = urllib.request.urlopen(_url_or_path)
                content = resource.read().decode(resource.headers.get_content_charset())
                return content
            except URLError as exp:
                print(f"URLError: {exp.reason} reading {_url_or_path}")
                return None
            except HTTPError as exp:
                print(f"HTTPError: {exp.reason} reading {_url_or_path}")
                return None
            except ValueError as exp:
                print(f"ValueError reading {_url_or_path}")
                return None
        else:
            if not os.path.exists(_url_or_path):
                return None

            try:
                f = open(_url_or_path, 'r')
                fc = f.read()
                f.close()
                return fc
            except:
                return None


def get_api_coverage(_sections):
    total_len = sum([len(x['section']) for x in _sections])
    wa = 0
    for i in range(len(_sections)):
        wa += (len(_sections[i]['section']) / total_len) * (_sections[i]['coverage'] / 100.0)
    return int(wa * 100)


def split_section(_to_splits, _that_split, _work_item_type):
    sections = []
    _work_items = []
    _current_work_item = _that_split[_work_item_type]
    _current_work_item['relation_id'] = _that_split['relation_id']
    _current_work_item['coverage'] = _that_split['coverage'] if 'coverage' in _that_split.keys() else 0
    _current_work_item['version'] = _that_split['version']

    for _to_split in _to_splits:
        _to_split_range = range(_to_split['offset'],
                                _to_split['offset'] + len(_to_split['section']))
        that_split_range = range(_that_split['offset'], _that_split['offset'] + len(_that_split['section']))
        overlap = len(list(set(_to_split_range) & set(that_split_range))) > 0
        if not overlap:
            tmp_section = {'section': _to_split['section'],
                           'offset': _to_split['offset'],
                           'coverage': _to_split['coverage'],
                           'delete': 0,
                           _Js: [],
                           _TCs: [],
                           _TSs: [],
                           _SRs: []}

            for j in range(len(_to_split[_SRs])):
                tmp_section[_SRs].append(_to_split[_SRs][j].copy())
            for j in range(len(_to_split[_TCs])):
                tmp_section[_TCs].append(_to_split[_TCs][j].copy())
            for j in range(len(_to_split[_TSs])):
                tmp_section[_TSs].append(_to_split[_TSs][j].copy())
            for j in range(len(_to_split[_Js])):
                tmp_section[_Js].append(_to_split[_Js][j].copy())

            sections.append(tmp_section)

        else:
            idx = [_to_split['offset'],
                   _to_split['offset'] + len(_to_split['section']),
                   _that_split['offset'],
                   _that_split['offset'] + len(_that_split['section'])]
            idx_set = set(idx)
            idx = sorted(list(idx_set))
            for i in range(1, len(idx)):
                tmp_section = {'section': _to_split['section'][idx[i - 1] - idx[0]:idx[i] - idx[0]],
                               'offset': idx[i - 1],
                               'coverage': _to_split['coverage'],
                               'delete': 0,
                               _Js: [],
                               _TCs: [],
                               _TSs: [],
                               _SRs: []}

                for j in range(len(_to_split[_SRs])):
                    tmp_section[_SRs].append(_to_split[_SRs][j].copy())
                for j in range(len(_to_split[_TCs])):
                    tmp_section[_TCs].append(_to_split[_TCs][j].copy())
                for j in range(len(_to_split[_TSs])):
                    tmp_section[_TSs].append(_to_split[_TSs][j].copy())
                for j in range(len(_to_split[_Js])):
                    tmp_section[_Js].append(_to_split[_Js][j].copy())
                sections.append(tmp_section)

    for iSection in range(len(sections)):
        section_range = range(sections[iSection]['offset'],
                              sections[iSection]['offset'] + len(sections[iSection]['section']))
        that_split_range = range(_that_split['offset'], _that_split['offset'] + len(_that_split['section']))
        overlap = len(list(set(section_range) & set(that_split_range))) > 0
        if overlap:
            sections[iSection][f'{_work_item_type}s'].append(_current_work_item)

    return sections


def get_splitted_sections(_specification, _mapping, _work_item_types):
    """
    _mapping: list of x_y (e.g. ApiSwRequirement) with nested mapping
              each row has its own specification section information
    _work_item_types: list of work items type for direct mapping that I
              what to display in the current view
    return: list of sections with related mapping
    """
    mapped_sections = [{'section': _specification,
                        'offset': 0,
                        'coverage': 0,
                        'delete': 0,
                        _TCs: [],
                        _TSs: [],
                        _SRs: [],
                        _Js: []}]

    for iWIT in range(len(_work_item_types)):
        _items_key = f"{_work_item_types[iWIT]}s"
        for iMapping in range(len(_mapping[_items_key])):
            if not _mapping[_items_key][iMapping]['match']:
                continue
            mapped_sections = sorted(mapped_sections, key=lambda k: k['offset'])
            # get overlapping sections
            overlapping_section_indexes = []
            for j in range(len(mapped_sections)):
                section_range = range(mapped_sections[j]['offset'],
                                      mapped_sections[j]['offset'] + len(mapped_sections[j]['section']))
                that_split_range = range(_mapping[_items_key][iMapping]['offset'],
                                         _mapping[_items_key][iMapping]['offset'] + len(
                                             _mapping[_items_key][iMapping]['section']))
                overlap = len(list(set(section_range) & set(that_split_range))) > 0
                if overlap:
                    overlapping_section_indexes.append(j)

            if len(overlapping_section_indexes) > 0:
                for k in overlapping_section_indexes:
                    mapped_sections[k]['delete'] = 1

                mapped_sections += split_section([x for x in mapped_sections if x['delete'] == 1],
                                                 _mapping[_items_key][iMapping], _work_item_types[iWIT])
                mapped_sections = [x for x in mapped_sections if x['delete'] == 0]

    for iS in range(len(mapped_sections)):
        if mapped_sections[iS]['section'].strip() == "":
            if sum([len(mapped_sections[iS][_SRs]),
                    len(mapped_sections[iS][_TSs]),
                    len(mapped_sections[iS][_TCs]),
                    len(mapped_sections[iS][_Js])]) == 0:
                mapped_sections[iS]['delete'] = True
        coverage_total = 0
        for j in range(len(mapped_sections[iS][_SRs])):
            coverage_total += mapped_sections[iS][_SRs][j]['coverage']
        for j in range(len(mapped_sections[iS][_TCs])):
            coverage_total += mapped_sections[iS][_TCs][j]['coverage']
        for j in range(len(mapped_sections[iS][_TSs])):
            coverage_total += mapped_sections[iS][_TSs][j]['coverage']
        for j in range(len(mapped_sections[iS][_Js])):
            coverage_total += mapped_sections[iS][_Js][j]['coverage']
        mapped_sections[iS]['coverage'] = min(max(coverage_total, 0), 100)

    # Remove Section with section: \n and no work items
    mapped_sections = [x for x in mapped_sections if not x['delete']]
    return sorted(mapped_sections, key=lambda k: k['offset'])


def check_fields_in_request(fields, request):
    for field in fields:
        if field not in request.keys():
            return False
    return True


def get_query_string_args(args):
    db = args.get("db", default="head", type=str)
    limit = args.get("limit", default="", type=str)
    order_by = args.get("order_by", default="", type=str)
    order_how = args.get("order_how", default="", type=str)

    permitted_keys = ["id", "api-id", "work_item_type", "mapped_to_type",
                      "relation_id", "mode", "search", "library",
                      "parent_table", "parent_id", "url"]
    ret = {"db": db,
           "limit": limit,
           "order_by": order_by,
           "order_how": order_how}

    i = 1
    while True:
        if args.get(f'field{i}') and args.get(f'filter{i}'):
            ret[f'field{i}'] = args.get(f'field{i}')
            ret[f'filter{i}'] = args.get(f'filter{i}')
            i = i + 1
        else:
            break

    if "join" in args.keys() and "join_id" in args.keys():
        ret["join"] = args.get("join")
        ret["join_id"] = args.get("join_id")

    for k in permitted_keys:
        if k in args.keys():
            ret[k] = args.get(k)

    return ret


def get_api_sw_requirements_mapping_sections(dbi, api):
    undesired_keys = ['section', 'offset']
    api_specification = get_api_specification(api.raw_specification_url)
    if api_specification == None:
        api_specification = "Unable to find the Software Specification. " \
                            "Please check the value in the Software Component properties" \
                            " or check your internet connection (If file is remote)."

    sr = dbi.session.query(ApiSwRequirementModel).filter(
        ApiSwRequirementModel.api_id == api.id).order_by(
        ApiSwRequirementModel.offset.asc()).all()
    sr_mapping = [x.as_dict(db_session=dbi.session) for x in sr]

    justifications = dbi.session.query(ApiJustificationModel).filter(
        ApiJustificationModel.api_id == api.id).order_by(
        ApiJustificationModel.offset.asc()).all()
    justifications_mapping = [x.as_dict(db_session=dbi.session) for x in justifications]

    mapping = {_A: api.as_dict(),
               _SRs: sr_mapping,
               _Js: justifications_mapping}

    for iSR in range(len(mapping[_SRs])):
        # Indirect Test Specifications
        curr_asr_id = mapping[_SRs][iSR]['relation_id']
        ind_ts = dbi.session.query(SwRequirementTestSpecificationModel).filter(
            SwRequirementTestSpecificationModel.sw_requirement_mapping_api_id == curr_asr_id
        ).all()
        mapping[_SRs][iSR][_SR][_TSs] = [get_dict_without_keys(x.as_dict(db_session=dbi.session),
                                                               undesired_keys + ['api']) for x in ind_ts]

        ind_tc = dbi.session.query(SwRequirementTestCaseModel).filter(
            SwRequirementTestCaseModel.sw_requirement_mapping_api_id == curr_asr_id
        ).all()
        mapping[_SRs][iSR][_SR][_TCs] = [get_dict_without_keys(x.as_dict(db_session=dbi.session),
                                                               undesired_keys + ['api', 'sw_requirement_mapping_api'])
                                         for x in ind_tc]

        for iTS in range(len(mapping[_SRs][iSR][_SR][_TSs])):
            # Indirect Test Cases
            curr_srts_id = mapping[_SRs][iSR][_SR][_TSs][iTS]['relation_id']
            ind_tc = dbi.session.query(TestSpecificationTestCaseModel).filter(
                TestSpecificationTestCaseModel.test_specification_mapping_sw_requirement_id == curr_srts_id
            ).all()

            mapping[_SRs][iSR][_SR][_TSs][iTS][_TS][_TCs] = [get_dict_without_keys(x.as_dict(db_session=dbi.session),
                                                                                   undesired_keys + ['api']) for x in
                                                             ind_tc]

    for iMapping in range(len(mapping[_SRs])):
        current_offset = mapping[_SRs][iMapping]['offset']
        current_section = mapping[_SRs][iMapping]['section']
        mapping[_SRs][iMapping]['match'] = (
                api_specification[current_offset:current_offset + len(current_section)] == current_section)
    for iMapping in range(len(mapping[_Js])):
        current_offset = mapping[_Js][iMapping]['offset']
        current_section = mapping[_Js][iMapping]['section']
        mapping[_Js][iMapping]['match'] = (
                api_specification[current_offset:current_offset + len(current_section)] == current_section)

    mapped_sections = get_splitted_sections(api_specification, mapping, [_SR, _J])
    unmapped_sections = [x for x in mapping[_SRs] if not x['match']]
    unmapped_sections += [x for x in mapping[_Js] if not x['match']]

    ret = {'mapped': mapped_sections,
           'unmapped': unmapped_sections}
    dbi.engine.dispose()
    return ret


def check_direct_work_items_against_another_spec_file(db_session, spec, api):
    ret = {'sw-requirements': {'ok': [],
                               'ko': [],
                               'warning': []},
           'test-specifications': {'ok': [],
                                   'ko': [],
                                   'warning': []},
           'test-cases': {'ok': [],
                          'ko': [],
                          'warning': []},
           'justifications': {'ok': [],
                              'ko': [],
                              'warning': []}
           }

    # ApiSwRequirement
    api_srs = db_session.query(ApiSwRequirementModel).filter(
        ApiSwRequirementModel.api_id == api.id
    ).all()
    for api_sr in api_srs:
        if api_sr.section in spec:
            if spec.index(api_sr.section) == api_sr.offset:
                ret['sw-requirements']['ok'].append({'id': api_sr.id,
                                                     'title': api_sr.sw_requirement.title})
            else:
                ret['sw-requirements']['warning'].append({'id': api_sr.id,
                                                          'old-offset': api_sr.offset,
                                                          'new-offset': spec.index(api_sr.section),
                                                          'title': api_sr.sw_requirement.title})
        else:
            ret['sw-requirements']['ko'].append({'id': api_sr.id,
                                                 'title': api_sr.sw_requirement.title})

    # ApiTestSpecification
    api_tss = db_session.query(ApiTestSpecificationModel).filter(
        ApiTestSpecificationModel.api_id == api.id
    ).all()
    for api_ts in api_tss:
        if api_ts.section in spec:
            if spec.index(api_ts.section) == api_ts.offset:
                ret['test-specifications']['ok'].append({'id': api_ts.id,
                                                         'title': api_ts.test_specification.title})
            else:
                ret['test-specifications']['warning'].append({'id': api_ts.id,
                                                              'old-offset': api_ts.offset,
                                                              'new-offset': spec.index(api_ts.section),
                                                              'title': api_ts.test_specification.title})
        else:
            ret['test-specifications']['ko'].append({'id': api_ts.id,
                                                     'title': api_ts.test_specification.title})

    # ApiTestCase
    api_tcs = db_session.query(ApiTestCaseModel).filter(
        ApiTestCaseModel.api_id == api.id
    ).all()
    for api_tc in api_tcs:
        if api_tc.section in spec:
            if spec.index(api_tc.section) == api_tc.offset:
                ret['test-cases']['ok'].append({'id': api_tc.id,
                                                'title': api_tc.test_case.title})
            else:
                ret['test-cases']['warning'].append({'id': api_tc.id,
                                                     'old-offset': api_tc.offset,
                                                     'new-offset': spec.index(
                                                         api_tc.section),
                                                     'title': api_tc.test_case.title})
        else:
            ret['test-cases']['ko'].append({'id': api_tc.id,
                                            'title': api_tc.test_case.title})

    # ApiJustification
    api_js = db_session.query(ApiJustificationModel).filter(
        ApiJustificationModel.api_id == api.id
    ).all()
    for api_j in api_js:
        if api_j.section in spec:
            if spec.index(api_j.section) == api_j.offset:
                ret['justifications']['ok'].append({'id': api_j.id,
                                                    'title': api_j.justification.description})
            else:
                ret['justifications']['warning'].append({'id': api_j.id,
                                                         'old-offset': api_j.offset,
                                                         'new-offset': spec.index(
                                                             api_j.section),
                                                         'title': api_j.justification.description})
        else:
            ret['justifications']['ko'].append({'id': api_j.id,
                                                'title': api_j.justification.description})
    return ret

class Token():

    def filter(self, token):
        if token == app.secret_key:
            return True
        return False


tokenManager = Token()


class SPDXLibrary(Resource):
    fields = ['library']

    def get(self):
        from spdx_manager import SPDXManager
        import datetime

        args = get_query_string_args(request.args)
        dbi = db_orm.DbInterface()

        query = dbi.session.query(ApiModel).filter(
            ApiModel.library == args['library']
        )
        apis = query.all()

        spdxManager = SPDXManager(f"SPDX-{args['library'].upper()}-EXPORT")
        for api in apis:
            spdxManager.add_api_to_export(api.id)
        dt = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        spdx_base_path = os.path.dirname(currentdir)
        spdx_relative_path = f"app{os.sep}public{os.sep}spdx_export"
        spdx_filename = f"{args['library']}-{dt}.json"
        spdx_filepath = os.path.join(spdx_base_path, spdx_relative_path, spdx_filename)
        for iRP in range(1, len(spdx_relative_path.split(os.sep))):
            currentRelativePath = os.sep.join(spdx_relative_path.split(os.sep)[:iRP+1])
            if not os.path.exists(os.path.join(spdx_base_path, currentRelativePath)):
                os.mkdir(os.path.join(spdx_base_path, currentRelativePath))

        spdxManager.export(spdx_filepath)

        return send_file(spdx_filepath)


class Comment(Resource):
    fields = ["comment", "parent_table", "username"]

    def get(self):
        mandatory_fields = ["parent_table", "parent_id"]
        args = get_query_string_args(request.args)

        if "parent_table" not in args.keys() or "parent_id" not in args.keys():
            return 'bad request!', 400

        dbi = db_orm.DbInterface()
        query = dbi.session.query(CommentModel).filter(
            CommentModel.parent_table == args["parent_table"]
        ).filter(
            CommentModel.parent_id == args["parent_id"]
        )

        if "search" in args:
            query = query.filter(or_(
                CommentModel.comment.like(f'%{args["search"]}%'),
                CommentModel.username.like(f'%{args["search"]}%')))

        query = query.order_by(CommentModel.created_at.asc())
        comments = [c.as_dict() for c in query.all()]

        dbi.engine.dispose()
        return comments

    def post(self):
        request_data = request.get_json(force=True)

        if not check_fields_in_request(self.fields, request_data):
            return 'bad request!', 400

        dbi = db_orm.DbInterface()

        parent_table = request_data['parent_table'].strip()
        if parent_table == "":
            return 'bad request!', 400

        parent_id = request_data['parent_id']
        if parent_id == "":
            return 'bad request!', 400

        comment = request_data['comment'].strip()
        if comment == "":
            return 'bad request!', 400

        username = request_data['username'].strip()
        if username == "":
            return 'bad request!', 400

        new_comment = CommentModel(parent_table, parent_id, username, comment)
        dbi.session.add(new_comment)

        dbi.session.commit()
        dbi.engine.dispose()
        return new_comment.as_dict()


class CheckSpecification(Resource):
    fields = ['id']

    def get(self):

        args = get_query_string_args(request.args)

        if not check_fields_in_request(self.fields, args):
            return 'bad request!', 400

        dbi = db_orm.DbInterface()

        query = dbi.session.query(ApiModel).filter(
            ApiModel.id == args['id']
        )
        apis = query.all()

        if len(apis) != 1:
            return "Unable to find the api", 400

        api = apis[0]

        if 'url' in args.keys():
            spec = get_api_specification(request.args['url'])
        else:
            spec = get_api_specification(api.raw_specification_url)

        ret = check_direct_work_items_against_another_spec_file(dbi.session, spec, api)
        dbi.engine.dispose()
        return ret


class FixNewSpecificationWarnings(Resource):
    fields = ['id']

    def get(self):

        args = get_query_string_args(request.args)

        if not check_fields_in_request(self.fields, args):
            return 'bad request!', 400

        dbi = db_orm.DbInterface()

        query = dbi.session.query(ApiModel).filter(
            ApiModel.id == args['id']
        )
        apis = query.all()

        if len(apis) != 1:
            return "Unable to find the api", 400

        api = apis[0]

        spec = get_api_specification(api.raw_specification_url)

        analysis = check_direct_work_items_against_another_spec_file(dbi.session, spec, api)

        #ApiSwRequirements
        for i in range(len(analysis['sw-requirements']['warning'])):
            sr_all = dbi.session.query(ApiSwRequirementModel).filter(
                ApiSwRequirementModel.id == analysis['sw-requirements']['warning'][i]['id']
            ).all()
            if len(sr_all) == 1:
                sr_all[0].offset = analysis['sw-requirements']['warning'][i]['new-offset']
                dbi.session.commit()

        # ApiTestSpecification
        for i in range(len(analysis['test-specifications']['warning'])):
            ts_all = dbi.session.query(ApiTestSpecificationModel).filter(
                ApiTestSpecificationModel.id == analysis['test-specifications']['warning'][i]['id']
            ).all()
            if len(ts_all) == 1:
                ts_all[0].offset = analysis['test-specifications']['warning'][i]['new-offset']
                dbi.session.commit()

        # ApiTestCase
        for i in range(len(analysis['test-cases']['warning'])):
            tc_all = dbi.session.query(ApiTestCaseModel).filter(
                ApiTestCaseModel.id == analysis['test-cases']['warning'][i]['id']
            ).all()
            if len(tc_all) == 1:
                tc_all[0].offset = analysis['test-cases']['warning'][i]['new-offset']
                dbi.session.commit()

        # ApiJustification
        for i in range(len(analysis['justifications']['warning'])):
            j_all = dbi.session.query(ApiJustificationModel).filter(
                ApiJustificationModel.id == analysis['justifications']['warning'][i]['id']
            ).all()
            if len(j_all) == 1:
                j_all[0].offset = analysis['justifications']['warning'][i]['new-offset']
                dbi.session.commit()

        dbi.engine.dispose()
        return True


class Api(Resource):
    fields = ["api", "library", "library-version",
              "raw-specification-url", "category",
              "implementation-file", "implementation-file-from-row",
              "implementation-file-to-row", "tags"]

    def get(self):
        """
        curl http://localhost:5000/api
        """
        apis_dict = []
        args = get_query_string_args(request.args)
        dbi = db_orm.DbInterface()

        query = dbi.session.query(ApiModel)

        for arg_key in args.keys():
            if "field" in arg_key:
                field_n = arg_key.replace('field', '')
                field = args[f'field{field_n}']
                filter = args[f'filter{field_n}']
                if field == 'name':
                    query = query.filter(ApiModel.api == filter)
                elif field == 'library':
                    query = query.filter(ApiModel.library == filter)
                elif field == 'id':
                    query = query.filter(ApiModel.id == filter)

            if arg_key == "search":
                query = query.filter(or_(ApiModel.api.like(f'%{args["search"]}%'),
                                         ApiModel.category.like(f'%{args["search"]}%'),
                                         ApiModel.tags.like(f'%{args["search"]}%'),
                                         ApiModel.library_version.like(f'%{args["search"]}%'),
                                         ApiModel.raw_specification_url.like(f'%{args["search"]}%'),
                                         ApiModel.implementation_file.like(f'%{args["search"]}%'),
                                         ))

        apis = query.all()

        if len(apis):
            apis_dict = [x.as_dict(db_session=dbi.session) for x in apis]

        total_coverage = -1
        for iApi in range(len(apis)):
            sections = get_api_sw_requirements_mapping_sections(dbi, apis[iApi])
            if sections is not None:
                if 'mapped' in sections.keys():
                    total_coverage = get_api_coverage(sections['mapped'])
                    apis_dict[iApi]['coverage'] = total_coverage

        if total_coverage == -1:
            total_coverage = 0

        ret = apis_dict
        ret = sorted(ret, key=lambda api: (api['api'], api['library_version']))
        dbi.engine.dispose()
        return ret

    def post(self):
        """
        add a new Api
        """
        request_data = request.get_json(force=True)

        if not check_fields_in_request(self.fields, request_data):
            return 'bad request!', 400

        dbi = db_orm.DbInterface()

        # Find api
        api = dbi.session.query(ApiModel).filter(
            ApiModel.api == request_data['api']
        ).filter(
            ApiModel.library == request_data['library']
        ).filter(
            ApiModel.library_version == request_data['library-version']
        ).all()

        if len(api) > 0:
            dbi.engine.dispose()
            return 'Api is already in the db for the selected library', 409

        if request_data['action'] == 'fork':
            source_api = dbi.session.query(ApiModel).filter(
                ApiModel.id == request_data['api-id']
            ).all()
            if len(source_api) != 1:
                return 'Source Api not found', 409
            if source_api[0].api != request_data['api']:
                return 'Source Api name differ from new Api name', 409
            if source_api[0].library != request_data['library']:
                return 'Source Api library differ from new Api library', 409

        new_api = ApiModel(request_data['api'],
                           request_data['library'],
                           request_data['library-version'],
                           request_data['raw-specification-url'],
                           request_data['category'],
                           request_data['implementation-file'],
                           request_data['implementation-file-from-row'],
                           request_data['implementation-file-to-row'],
                           request_data['tags'], )

        dbi.session.add(new_api)

        if request_data['action'] == 'fork':
            dbi.session.commit()  # to read the id

            # Clone ApiJustification
            api_justifications = dbi.session.query(ApiJustificationModel).filter(
                ApiJustificationModel.api_id == source_api[0].id
            ).all()
            for api_justification in api_justifications:
                tmp = ApiJustificationModel(new_api,
                                            api_justification.justification,
                                            api_justification.section,
                                            api_justification.offset,
                                            api_justification.coverage)
                dbi.session.add(tmp)

            # Clone ApiSwRequirement
            api_sw_requirements = dbi.session.query(ApiSwRequirementModel).filter(
                ApiSwRequirementModel.api_id == source_api[0].id
            ).all()
            for api_sw_requirement in api_sw_requirements:
                tmp = ApiSwRequirementModel(new_api,
                                            api_sw_requirement.sw_requirement,
                                            api_sw_requirement.section,
                                            api_sw_requirement.offset,
                                            api_sw_requirement.coverage)
                dbi.session.add(tmp)

            # Clone ApiTestSpecification
            api_test_specifications = dbi.session.query(ApiTestSpecificationModel).filter(
                ApiTestSpecificationModel.api_id == source_api[0].id
            ).all()
            for api_test_specification in api_test_specifications:
                tmp = ApiTestSpecificationModel(new_api,
                                                api_test_specification.test_specification,
                                                api_test_specification.section,
                                                api_test_specification.offset,
                                                api_test_specification.coverage)
                dbi.session.add(tmp)

            # Clone ApiTestCase
            api_test_cases = dbi.session.query(ApiTestCaseModel).filter(
                ApiTestCaseModel.api_id == source_api[0].id
            ).all()
            for api_test_case in api_test_cases:
                tmp = ApiTestCaseModel(new_api,
                                       api_test_case.test_case,
                                       api_test_case.section,
                                       api_test_case.offset,
                                       api_test_case.coverage)
                dbi.session.add(tmp)

        dbi.session.commit()
        dbi.engine.dispose()
        return new_api.as_dict()

    def put(self):
        """
        edit an existing Api
        """

        request_data = request.get_json(force=True)
        put_fields = self.fields.copy()
        put_fields.append('api-id')
        if not check_fields_in_request(put_fields, request_data):
            return 'bad request!', 400

        dbi = db_orm.DbInterface()

        # Find api
        api = get_api_from_request(request_data, dbi.session)

        if not api:
            dbi.engine.dispose()
            return 'Api not in the db', 404

        # Check that the new api+library+library_version is not already in the db
        same_existing_apis = dbi.session.query(ApiModel).filter(
            ApiModel.api == request_data['api']
        ).filter(
            ApiModel.library == request_data['library']
        ).filter(
            ApiModel.library == request_data['library-version']
        ).filter(
            ApiModel.id != request_data['api-id']).all()

        if len(same_existing_apis) > 0:
            dbi.engine.dispose()
            return 'An Api with selected name and library already exist in the db', 409

        if request_data['api'] != api.api:
            api.api = request_data['api']

        if request_data['library'] != api.library:
            api.library = request_data['library']

        if request_data['library-version'] != api.library:
            api.library_version = request_data['library-version']

        if request_data['raw-specification-url'] != api.raw_specification_url:
            api.raw_specification_url = request_data['raw-specification-url']

        if request_data['category'] != api.category:
            api.category = request_data['category']

        if request_data['implementation-file'] != api.implementation_file:
            api.implementation_file = request_data['implementation-file']

        if request_data['implementation-file-from-row'] != api.implementation_file_from_row:
            api.implementation_file_from_row = request_data['implementation-file-from-row']

        if request_data['implementation-file-to-row'] != api.implementation_file_to_row:
            api.implementation_file_to_row = request_data['implementation-file-to-row']

        if request_data['tags'] != api.tags:
            api.tags = request_data['tags']

        dbi.session.commit()
        dbi.engine.dispose()
        return api.as_dict()


class ApiHistory(Resource):
    def get(self):
        args = get_query_string_args(request.args)

        if 'api-id' not in args.keys():
            return []

        dbi = db_orm.DbInterface()

        _model = ApiModel
        _model_history = ApiHistoryModel
        _model_fields = _model.__table__.columns.keys()

        model_versions_query = dbi.session.query(_model_history).filter(
            _model_history.id == args['api-id']).order_by(
            _model_history.version.asc())
        staging_array = []
        ret = []

        # object dict
        for model_version in model_versions_query.all():
            _description = ''

            obj = {"version": model_version.version,
                   "type": "object",
                   "created_at": datetime.strptime(str(model_version.created_at), '%Y-%m-%d %H:%M:%S.%f')}

            for k in _model_fields:
                if k not in ['row_id', 'version', 'created_at', 'updated_at']:
                    obj[k] = getattr(model_version, k)

            staging_array.append(obj)

        staging_array = sorted(staging_array, key=lambda d: (d['created_at']))

        # get version object.mapping equal to 1.1
        first_found = False
        first_obj = {}
        for i in range(len(staging_array)):
            if staging_array[i]['version'] == 1 and staging_array[i]['type'] == 'object':
                first_obj = staging_array[i]
                first_found = True
                break

        if not first_found:
            dbi.engine.dispose()
            return []

        ret.append(get_combined_history_object(first_obj, {}, _model_fields, []))

        for i in range(len(staging_array)):
            last_obj_version = int(ret[-1]['version'].split(".")[0])
            if staging_array[i]['type'] == 'object' and staging_array[i]['version'] > last_obj_version:
                ret.append(get_combined_history_object(staging_array[i], ret[-1]['mapping'], _model_fields, []))

        ret = get_reduced_history_data(ret, _model_fields, [])
        ret = ret[::-1]
        dbi.engine.dispose()
        return ret


class Library(Resource):

    def get(self):
        """
        curl http://localhost:5000/api
        """

        # args = get_query_string_args(request.args)
        dbi = db_orm.DbInterface()
        libraries = dbi.session.query(ApiModel.library).distinct().all()
        dbi.engine.dispose()
        return sorted([x.library for x in libraries])


class ApiSpecification(Resource):
    def get(self):
        """
                curl http://localhost:5000/api
                """

        args = get_query_string_args(request.args)
        if "api-id" not in args.keys():
            return {}

        dbi = db_orm.DbInterface()

        api = get_api_from_request(args, dbi.session)
        if not api:
            dbi.engine.dispose()
            return "Api not found", 404

        spec = get_api_specification(api.raw_specification_url)

        ret = api.as_dict()
        ret['raw_specification'] = spec
        dbi.engine.dispose()
        return ret


class ApiTestSpecificationsMapping(Resource):
    fields = ['api-id', 'test-specification', 'section', 'coverage']

    def get(self):
        """
        curl <API_URL>/api/test-specifications?api-id=<api-id>
        """
        args = get_query_string_args(request.args)
        if not check_fields_in_request(['api-id'], args):
            return 'bad request!', 400

        undesired_keys = ['section', 'offset']

        dbi = db_orm.DbInterface()

        # Find api
        api = get_api_from_request(args, dbi.session)
        if not api:
            dbi.engine.dispose()
            return "Api not found", 404

        api_specification = get_api_specification(api.raw_specification_url)
        if api_specification == None:
            return []

        ts = dbi.session.query(ApiTestSpecificationModel).filter(
            ApiTestSpecificationModel.api_id == api.id).order_by(
            ApiTestSpecificationModel.offset.asc()).all()
        ts_mapping = [x.as_dict(db_session=dbi.session) for x in ts]

        justifications = dbi.session.query(ApiJustificationModel).filter(
            ApiJustificationModel.api_id == api.id).order_by(
            ApiJustificationModel.offset.asc()).all()
        justifications_mapping = [x.as_dict(db_session=dbi.session) for x in justifications]

        mapping = {_A: api.as_dict(),
                   _TSs: ts_mapping,
                   _Js: justifications_mapping}

        for iTS in range(len(mapping[_TSs])):
            # Indirect Test Cases
            curr_ats_id = mapping[_TSs][iTS]['relation_id']

            ind_tc = dbi.session.query(TestSpecificationTestCaseModel).filter(
                TestSpecificationTestCaseModel.test_specification_mapping_api_id == curr_ats_id
            ).all()
            mapping[_TSs][iTS][_TS][_TCs] = [get_dict_without_keys(x.as_dict(db_session=dbi.session),
                                                                   undesired_keys + ['api']) for x in ind_tc]

        for iMapping in range(len(mapping[_TSs])):
            current_offset = mapping[_TSs][iMapping]['offset']
            current_section = mapping[_TSs][iMapping]['section']
            mapping[_TSs][iMapping]['match'] = (
                    api_specification[current_offset:current_offset + len(current_section)] == current_section)
        for iMapping in range(len(mapping[_Js])):
            current_offset = mapping[_Js][iMapping]['offset']
            current_section = mapping[_Js][iMapping]['section']
            mapping[_Js][iMapping]['match'] = (
                    api_specification[current_offset:current_offset + len(current_section)] == current_section)

        mapped_sections = get_splitted_sections(api_specification, mapping, [_TS, _J])
        unmapped_sections = [x for x in mapping[_TSs] if not x['match']]
        unmapped_sections += [x for x in mapping[_Js] if not x['match']]
        ret = {'mapped': mapped_sections,
               'unmapped': unmapped_sections}

        dbi.engine.dispose()
        return ret

    def post(self):
        request_data = request.get_json(force=True)

        if not check_fields_in_request(self.fields, request_data):
            return 'bad request!', 400

        dbi = db_orm.DbInterface()

        # Find api
        api = get_api_from_request(request_data, dbi.session)
        if not api:
            dbi.engine.dispose()
            return "Api not found", 404

        section = request_data['section']
        offset = request_data['offset']
        coverage = request_data['coverage']

        # Re using existing test case
        if 'id' not in request_data['test-specification'].keys():
            # Create a new one
            for check_field in TestSpecification.fields:
                if check_field.replace("_", "-") not in request_data['test-specification'].keys():
                    dbi.engine.dispose()
                    return "Bad request. Unconsistend data.", 400

            title = request_data['test-specification']['title']
            preconditions = request_data['test-specification']['preconditions']
            test_description = request_data['test-specification']['test-description']
            expected_behavior = request_data['test-specification']['expected-behavior']

            if len(dbi.session.query(TestSpecificationModel).filter(
                    TestSpecificationModel.title == title).filter(
                TestSpecificationModel.preconditions == preconditions).filter(
                TestSpecificationModel.test_description == test_description).filter(
                TestSpecificationModel.expected_behavior == expected_behavior).all()) > 0:
                dbi.engine.dispose()
                return "Test Specification already associated to the selected api Specification section.", 409

            new_test_specification = TestSpecificationModel(request_data['test-specification']['title'],
                                                            request_data['test-specification']['preconditions'],
                                                            request_data['test-specification']['test-description'],
                                                            request_data['test-specification']['expected-behavior'])
            new_test_specification_mapping_api = ApiTestSpecificationModel(api,
                                                                           new_test_specification,
                                                                           section,
                                                                           offset,
                                                                           coverage)

            dbi.session.add(new_test_specification)
            dbi.session.add(new_test_specification_mapping_api)

        else:
            id = request_data['test-specification']['id']
            if len(dbi.session.query(ApiTestSpecificationModel).filter(
                    ApiTestSpecificationModel.api_id == api.id).filter(
                ApiTestSpecificationModel.test_specification_id == id).filter(
                ApiTestSpecificationModel.section == section).all()) > 0:
                dbi.engine.dispose()
                return "Test Specification already associated to the selected api Specification section.", 409

            existing_test_specification = dbi.session.query(TestSpecificationModel).filter(
                TestSpecificationModel.id == id).one()

            new_test_specification_mapping_api = ApiTestSpecificationModel(api,
                                                                           existing_test_specification,
                                                                           section,
                                                                           offset,
                                                                           coverage)
            dbi.session.add(new_test_specification_mapping_api)

        dbi.session.commit()
        dbi.engine.dispose()
        return new_test_specification_mapping_api.as_dict()

    def put(self):

        request_data = request.get_json(force=True)

        if not check_fields_in_request(self.fields, request_data):
            return 'bad request!', 400

        dbi = db_orm.DbInterface()

        # Find api
        api = get_api_from_request(request_data, dbi.session)
        if not api:
            dbi.engine.dispose()
            return "Api not found", 404

        test_specification_mapping_api = dbi.session.query(ApiTestSpecificationModel).filter(
            ApiTestSpecificationModel.id == request_data["relation-id"]).one()
        test_specification = test_specification_mapping_api.test_specification

        # Update only modified fields
        if test_specification.title != request_data["test-specification"]["title"]:
            test_specification.title = request_data["test-specification"]["title"]

        if test_specification.preconditions != request_data["test-specification"]["preconditions"]:
            test_specification.preconditions = request_data["test-specification"]["preconditions"]

        if test_specification.test_description != request_data["test-specification"]["test-description"]:
            test_specification.test_description = request_data["test-specification"]["test-description"]

        if test_specification.expected_behavior != request_data["test-specification"]["expected-behavior"]:
            test_specification.expected_behavior = request_data["test-specification"]["expected-behavior"]

        if test_specification_mapping_api.section != request_data["section"]:
            test_specification_mapping_api.section = request_data["section"]

        if test_specification_mapping_api.offset != request_data["offset"]:
            test_specification_mapping_api.offset = request_data["offset"]

        if test_specification_mapping_api.coverage != int(request_data["coverage"]):
            test_specification_mapping_api.coverage = int(request_data["coverage"])

        dbi.session.commit()
        dbi.engine.dispose()
        return test_specification_mapping_api.as_dict()

    def delete(self):
        request_data = request.get_json(force=True)

        if not check_fields_in_request(['relation-id', 'api-id'], request_data):
            return 'bad request!', 400

        dbi = db_orm.DbInterface()

        # Find api
        api = get_api_from_request(request_data, dbi.session)
        if not api:
            dbi.engine.dispose()
            return "Api not found", 404

        # check if api ...
        test_specification_mapping_api = dbi.session.query(ApiTestSpecificationModel).filter(
            ApiTestSpecificationModel.id == request_data["relation-id"]).one()
        if test_specification_mapping_api.api.id != api.id:
            dbi.engine.dispose()
            return 'bad request!', 401

        dbi.session.delete(test_specification_mapping_api)

        # TODO: Remove work item only user request to do
        """
        test_specification = test_specification_mapping_api.test_specification

        if len(dbi.session.query(ApiTestSpecificationModel).filter( \
                ApiTestSpecificationModel.api_id == api.id).filter( \
                ApiTestSpecificationModel.test_specification_id == test_specification.id).all()) == 0:
            dbi.session.delete(test_specification)
        """

        dbi.session.commit()
        dbi.engine.dispose()
        return True


class ApiTestCasesMapping(Resource):
    fields = ['api-id', 'test-case', 'section', 'coverage']

    def get(self):
        """
        curl <API_URL>/api/test-cases?api-id=<api-id>
        """

        args = get_query_string_args(request.args)
        if not check_fields_in_request(['api-id'], args):
            return 'bad request!', 400

        undesired_keys = ['section', 'offset']

        dbi = db_orm.DbInterface()

        # Find api
        api = get_api_from_request(args, dbi.session)
        if not api:
            dbi.engine.dispose()
            return "Api not found", 404

        api_specification = get_api_specification(api.raw_specification_url)
        if api_specification is None:
            return []

        tc = dbi.session.query(ApiTestCaseModel).filter(
            ApiTestCaseModel.api_id == api.id).order_by(
            ApiTestCaseModel.offset.asc()).all()
        tc_mapping = [x.as_dict(db_session=dbi.session) for x in tc]

        justifications = dbi.session.query(ApiJustificationModel).filter(
            ApiJustificationModel.api_id == api.id).order_by(
            ApiJustificationModel.offset.asc()).all()
        justifications_mapping = [x.as_dict(db_session=dbi.session) for x in justifications]

        mapping = {_A: api.as_dict(),
                   _TCs: tc_mapping,
                   _Js: justifications_mapping}

        for iMapping in range(len(mapping[_TCs])):
            current_offset = mapping[_TCs][iMapping]['offset']
            current_section = mapping[_TCs][iMapping]['section']
            mapping[_TCs][iMapping]['match'] = (
                    api_specification[current_offset:current_offset + len(current_section)] == current_section)
        for iMapping in range(len(mapping[_Js])):
            current_offset = mapping[_Js][iMapping]['offset']
            current_section = mapping[_Js][iMapping]['section']
            mapping[_Js][iMapping]['match'] = (
                    api_specification[current_offset:current_offset + len(current_section)] == current_section)

        mapped_sections = get_splitted_sections(api_specification, mapping, [_TC, _J])
        unmapped_sections = [x for x in mapping[_TCs] if not x['match']]
        unmapped_sections += [x for x in mapping[_Js] if not x['match']]
        ret = {'mapped': mapped_sections,
               'unmapped': unmapped_sections}

        dbi.engine.dispose()
        return ret

    def post(self):
        request_data = request.get_json(force=True)

        if not check_fields_in_request(self.fields, request_data):
            return 'bad request!', 400

        dbi = db_orm.DbInterface()

        # Find api
        api = get_api_from_request(request_data, dbi.session)
        if not api:
            dbi.engine.dispose()
            return "Api not found", 404

        section = request_data['section']
        offset = request_data['offset']
        coverage = request_data['coverage']

        # Re using existing test case
        if 'id' not in request_data['test-case'].keys():
            # Create a new one
            for check_field in TestCase.fields:
                if check_field.replace("_", "-") not in request_data['test-case'].keys():
                    dbi.engine.dispose()
                    return "Bad request. Not consistent data.", 400

            repository = request_data['test-case']['repository']
            relative_path = request_data['test-case']['relative-path']
            title = request_data['test-case']['title']
            description = request_data['test-case']['description']

            # Check if the same Test Case is already associated with the same snippet
            if len(dbi.session.query(ApiTestCaseModel).join(TestCaseModel).filter(
                    ApiTestCaseModel.section == section).filter(
                TestCaseModel.repository == repository).filter(
                TestCaseModel.relative_path == relative_path).all()) > 0:
                dbi.engine.dispose()
                return "Test Case already associated to the current api.", 409

            new_test_case = TestCaseModel(repository, relative_path,
                                          title, description)

            new_test_case_mapping_api = ApiTestCaseModel(api,
                                                         new_test_case,
                                                         section,
                                                         offset,
                                                         coverage)
            dbi.session.add(new_test_case)
            dbi.session.add(new_test_case_mapping_api)
        else:
            id = request_data['test-case']['id']
            if len(dbi.session.query(ApiTestCaseModel).filter(ApiTestCaseModel.api_id == api.id).filter(
                    ApiTestCaseModel.test_case_id == id).filter(ApiTestCaseModel.section == section).all()) > 0:
                dbi.engine.dispose()
                return "Test Case already associated to the selected api Specification section.", 409

            existing_test_case = dbi.session.query(TestCaseModel).filter(TestCaseModel.id == id).one()
            new_test_case_mapping_api = ApiTestCaseModel(api,
                                                         existing_test_case,
                                                         section,
                                                         offset,
                                                         coverage)

            dbi.session.add(new_test_case_mapping_api)

        dbi.session.commit()
        dbi.engine.dispose()
        return new_test_case_mapping_api.as_dict()

    def put(self):
        request_data = request.get_json(force=True)

        if not check_fields_in_request(self.fields, request_data):
            return 'bad request!', 400

        dbi = db_orm.DbInterface()

        # Find api
        api = get_api_from_request(request_data, dbi.session)
        if not api:
            dbi.engine.dispose()
            return "Api not found", 404

        try:
            test_case_mapping_api = dbi.session.query(ApiTestCaseModel).filter(
                ApiTestCaseModel.id == request_data["relation-id"]).one()
            test_case = test_case_mapping_api.test_case
        except:
            dbi.engine.dispose()
            return "Test Case mapping api not found", 400

        # Update only modified fields
        if test_case.title != request_data["test-case"]["title"]:
            test_case.title = request_data["test-case"]["title"]

        if test_case.description != request_data["test-case"]["description"]:
            test_case.description = request_data["test-case"]["description"]

        if test_case.repository != request_data["test-case"]["repository"]:
            test_case.repository = request_data["test-case"]["repository"]

        if test_case.relative_path != request_data["test-case"]["relative-path"]:
            test_case.relative_path = request_data["test-case"]["relative-path"]

        if test_case_mapping_api.section != request_data["section"]:
            test_case_mapping_api.section = request_data["section"]

        if test_case_mapping_api.offset != request_data["offset"]:
            test_case_mapping_api.offset = request_data["offset"]

        if test_case_mapping_api.coverage != int(request_data["coverage"]):
            test_case_mapping_api.coverage = int(request_data["coverage"])

        dbi.session.commit()
        dbi.engine.dispose()
        return test_case_mapping_api.as_dict()

    def delete(self):
        request_data = request.get_json(force=True)

        if not check_fields_in_request(['relation-id', 'api-id'], request_data):
            return 'bad request!', 400

        dbi = db_orm.DbInterface()

        # Find api
        api = get_api_from_request(request_data, dbi.session)
        if not api:
            dbi.engine.dispose()
            return "Api not found", 404

        # check if api ...
        test_case_mapping_api = dbi.session.query(ApiTestCaseModel).filter(
            ApiTestCaseModel.id == request_data["relation-id"]).one()
        if test_case_mapping_api.api.id != api.id:
            dbi.engine.dispose()
            return 'bad request!', 401

        dbi.session.delete(test_case_mapping_api)

        # TODO: Remove work item only user request to do
        """
        test_case = test_case_mapping_api.test_case

        if len(dbi.session.query(ApiTestCaseModel).filter( \
                ApiTestCaseModel.api_id == api.id).filter( \
                ApiTestCaseModel.test_case_id == test_case.id).all()) == 0:
            dbi.session.delete(test_case)
        """

        dbi.session.commit()
        dbi.engine.dispose()
        return True


class MappingHistory(Resource):
    def get(self):
        args = get_query_string_args(request.args)
        dbi = db_orm.DbInterface()

        if 'work_item_type' not in args.keys() or 'mapped_to_type' not in args.keys() or 'relation_id' not in args.keys():
            dbi.engine.dispose()
            return []

        if args['mapped_to_type'] == "api":
            if args['work_item_type'] == 'justification':
                _model = JustificationModel
                _model_map = ApiJustificationModel
                _model_map_history = ApiJustificationHistoryModel
                _model_history = JustificationHistoryModel
            elif args['work_item_type'] == 'sw-requirement':
                _model = SwRequirementModel
                _model_map = ApiSwRequirementModel
                _model_map_history = ApiSwRequirementHistoryModel
                _model_history = SwRequirementHistoryModel
            elif args['work_item_type'] == 'test-specification':
                _model = TestSpecificationModel
                _model_map = ApiTestSpecificationModel
                _model_map_history = ApiTestSpecificationHistoryModel
                _model_history = TestSpecificationHistoryModel
            elif args['work_item_type'] == 'test-case':
                _model = TestCaseModel
                _model_map = ApiTestCaseModel
                _model_map_history = ApiTestCaseHistoryModel
                _model_history = TestCaseHistoryModel
            else:
                dbi.engine.dispose()
                return []

        elif args['mapped_to_type'] == "sw-requirement":
            if args['work_item_type'] == 'test-specification':
                _model = TestSpecificationModel
                _model_map = SwRequirementTestSpecificationModel
                _model_map_history = SwRequirementTestSpecificationHistoryModel
                _model_history = TestSpecificationHistoryModel
            elif args['work_item_type'] == 'test-case':
                _model = TestCaseModel
                _model_map = SwRequirementTestCaseModel
                _model_map_history = SwRequirementTestCaseHistoryModel
                _model_history = TestCaseHistoryModel
            else:
                dbi.engine.dispose()
                return []

        elif args['mapped_to_type'] == "test-specification":
            if args['work_item_type'] == 'test-case':
                _model = TestCaseModel
                _model_map = TestSpecificationTestCaseModel
                _model_map_history = TestSpecificationTestCaseHistoryModel
                _model_history = TestCaseHistoryModel
            else:
                dbi.engine.dispose()
                return []
        else:
            dbi.engine.dispose()
            return []

        _model_fields = _model.__table__.columns.keys()
        _model_map_fields = _model_map.__table__.columns.keys()

        relation_rows = dbi.session.query(_model_map).filter(_model_map.id == args['relation_id']).all()
        if len(relation_rows) != 1:
            dbi.engine.dispose()
            return []

        relation_row = relation_rows[0].as_dict()

        model_versions_query = dbi.session.query(_model_history).filter(
            _model_history.id == relation_row[args['work_item_type'].replace('-', '_')]['id']).order_by(
            _model_history.version.asc())
        model_map_versions_query = dbi.session.query(_model_map_history).filter(
            _model_map_history.id == args['relation_id']).order_by(
            _model_map_history.version.asc())

        staging_array = []
        ret = []

        # object dict
        for model_version in model_versions_query.all():
            _description = ''

            obj = {"version": model_version.version,
                   "type": "object",
                   "created_at": datetime.strptime(str(model_version.created_at), '%Y-%m-%d %H:%M:%S.%f')}

            for k in _model_fields:
                if k not in ['row_id', 'version', 'created_at', 'updated_at']:
                    obj[k] = getattr(model_version, k)

            staging_array.append(obj)

        # map dict
        for model_map_version in model_map_versions_query.all():
            _description = ''

            obj = {"version": model_map_version.version,
                   "type": "mapping",
                   "created_at": datetime.strptime(str(model_map_version.created_at),
                                                   '%Y-%m-%d %H:%M:%S.%f')}
            for k in _model_map_fields:
                if args['work_item_type'] == 'justification':
                    if k not in ['coverage', 'created_at', 'updated_at']:
                        obj[k] = getattr(model_map_version, k)
                else:
                    if k not in ['created_at', 'updated_at']:
                        obj[k] = getattr(model_map_version, k)

            staging_array.append(obj)

        staging_array = sorted(staging_array, key=lambda d: (d['created_at']))

        # get version object.mapping equal to 1.1
        first_found = False
        first_obj = {}
        first_map = {}

        for i in range(len(staging_array)):
            if staging_array[i]['version'] == 1 and staging_array[i]['type'] == 'object':
                first_obj = staging_array[i]
            elif staging_array[i]['version'] == 1 and staging_array[i]['type'] == 'mapping':
                first_map = staging_array[i]
            if first_map != {} and first_obj != {}:
                first_found = True
                break

        if not first_found:
            dbi.engine.dispose()
            return []

        ret.append(get_combined_history_object(first_obj, first_map, _model_fields, _model_map_fields))

        for i in range(len(staging_array)):
            last_obj_version = int(ret[-1]['version'].split(".")[0])
            last_map_version = int(ret[-1]['version'].split(".")[1])
            if staging_array[i]['type'] == 'object' and staging_array[i]['version'] > last_obj_version:
                ret.append(
                    get_combined_history_object(staging_array[i], ret[-1]['mapping'], _model_fields, _model_map_fields))
            elif staging_array[i]['type'] == 'mapping' and staging_array[i]['version'] > last_map_version:
                ret.append(
                    get_combined_history_object(ret[-1]['object'], staging_array[i], _model_fields, _model_map_fields))

        ret = get_reduced_history_data(ret, _model_fields, _model_map_fields)
        ret = ret[::-1]
        dbi.engine.dispose()
        return ret


class MappingUsage(Resource):
    def get(self):
        """ Return list of api the selected work item is mapped directly against
            Improvement: Take in consideration also indirect mapping and other
              work items, like list of Test Specifications where a Test Case
              is used
        """
        args = get_query_string_args(request.args)
        dbi = db_orm.DbInterface()

        if 'work_item_type' not in args.keys() or 'id' not in args.keys():
            dbi.engine.dispose()
            return []

        _id = args['id']

        # Api
        if args['work_item_type'] == "justification":
            model = ApiJustificationModel
            api_data = dbi.session.query(model).filter(
                model.justification_id == _id
            ).all()
            api_ids = [x.api_id for x in api_data]
        elif args['work_item_type'] == "sw-requirement":
            model = ApiSwRequirementModel
            api_data = dbi.session.query(model).filter(
                model.sw_requirement_id == _id
            ).all()
            api_ids = [x.api_id for x in api_data]
        elif args['work_item_type'] == "test-specification":
            # Direct
            model = ApiTestSpecificationModel
            api_data = dbi.session.query(model).filter(
                model.test_specification_id == _id
            ).all()
            api_ids = [x.api_id for x in api_data]

            # indirect sw requirement mapping api:
            model = SwRequirementTestSpecificationModel
            parent_model = ApiSwRequirementModel
            sr_api_data = dbi.session.query(model).join(parent_model).filter(
                model.test_specification_id == _id
            ).all()
            api_ids += [x.sw_requirement_mapping_api.api_id for x in sr_api_data]
        elif args['work_item_type'] == "test-case":
            model = ApiTestCaseModel
            api_data = dbi.session.query(model).filter(
                model.test_case_id == _id
            ).all()
            api_ids = [x.api_id for x in api_data]

            # indirect test specification mapping api:
            model = TestSpecificationTestCaseModel
            parent_model = ApiTestSpecificationModel
            ts_api_data = dbi.session.query(model).join(parent_model).filter(
                model.test_case_id == _id
            ).all()
            api_ids += [x.sw_requirement_mapping_api.api_id for x in ts_api_data]

            # indirect sw requirement mapping api:
            model = SwRequirementTestCaseModel
            parent_model = ApiSwRequirementModel
            sr_api_data = dbi.session.query(model).join(parent_model).filter(
                model.test_case_id == _id
            ).all()
            api_ids += [x.sw_requirement_mapping_api.api_id for x in sr_api_data]

            # indirect test specification sw requirement:
            model = TestSpecificationTestCaseModel
            parent_model = SwRequirementTestSpecificationModel
            sr_ts_data = dbi.session.query(model).join(parent_model).filter(
                model.test_case_id == _id
            ).all()
            sr_ts_ids = [x.test_specification_mapping_sw_requirement_id for x in sr_ts_data]
            model = SwRequirementTestSpecificationModel
            parent_model = ApiSwRequirementModel
            sr_api_data = dbi.session.query(model).join(parent_model).filter(
                model.sw_requirement_mapping_api_id.in_(sr_ts_ids)).all()
            api_ids += [x.sw_requirement_mapping_api.api_id for x in sr_api_data]

        apis = dbi.session.query(ApiModel).filter(
            ApiModel.id.in_(api_ids)
        ).all()

        query_data = {'api': [{'id': x.id,
                               'api': x.api,
                               'library': x.library,
                               'library_version': x.library_version} for x in apis]}

        return query_data


class ApiSpecificationsMapping(Resource):
    fields = ['api-id', 'justification', 'section', 'offset']

    def get(self):
        """
        curl <API_URL>/api/specifications?api-id=<api-id>
        """

        args = get_query_string_args(request.args)
        if not check_fields_in_request(['api-id'], args):
            return 'bad request!', 400

        undesired_keys = ['section', 'offset']

        dbi = db_orm.DbInterface()

        # Find api
        api = get_api_from_request(args, dbi.session)
        if not api:
            dbi.engine.dispose()
            return "Api not found", 404

        api_specification = get_api_specification(api.raw_specification_url)
        if api_specification == None:
            return []

        mapped_sections = [{'section': api_specification,
                            'offset': 0,
                            'coverage': 0,
                            _TCs: [],
                            _TSs: [],
                            _SRs: [],
                            _Js: []}]

        unmapped_sections = []
        ret = {'mapped': mapped_sections,
               'unmapped': unmapped_sections}

        dbi.engine.dispose()
        return ret


class ApiJustificationsMapping(Resource):
    fields = ['api-id', 'justification', 'section', 'offset', 'coverage']

    def get(self):
        """
        curl <API_URL>/api/justifications?api-id=<api-id>
        """

        args = get_query_string_args(request.args)
        if not check_fields_in_request(['api-id'], args):
            return 'bad request!', 400

        undesired_keys = ['section', 'offset']

        dbi = db_orm.DbInterface()

        # Find api
        api = get_api_from_request(args, dbi.session)
        if not api:
            dbi.engine.dispose()
            return "Api not found", 404

        api_specification = get_api_specification(api.raw_specification_url)
        if api_specification == None:
            return []

        justifications = dbi.session.query(ApiJustificationModel).filter(
            ApiJustificationModel.api_id == api.id).order_by(
            ApiJustificationModel.offset.asc()).all()
        justifications_mapping = [x.as_dict(db_session=dbi.session) for x in justifications]

        mapping = {_A: api.as_dict(),
                   _Js: justifications_mapping}

        for iMapping in range(len(mapping[_Js])):
            current_offset = mapping[_Js][iMapping]['offset']
            current_section = mapping[_Js][iMapping]['section']
            mapping[_Js][iMapping]['match'] = (
                    api_specification[current_offset:current_offset + len(current_section)] == current_section)

        mapped_sections = get_splitted_sections(api_specification, mapping, [_J])
        unmapped_sections = [x for x in mapping[_Js] if not x['match']]
        ret = {'mapped': mapped_sections,
               'unmapped': unmapped_sections}

        dbi.engine.dispose()
        return ret

    def post(self):
        request_data = request.get_json(force=True)

        if not check_fields_in_request(self.fields, request_data):
            return 'bad request!', 400

        dbi = db_orm.DbInterface()

        # Find api
        api = get_api_from_request(request_data, dbi.session)
        if not api:
            dbi.engine.dispose()
            return "Api not found", 404

        section = request_data['section']
        offset = request_data['offset']
        coverage = request_data['coverage']

        if 'id' not in request_data['justification'].keys():
            description = request_data['justification']['description']
            new_justification = JustificationModel(description)
            new_justification_mapping_api = ApiJustificationModel(api,
                                                                  new_justification,
                                                                  section,
                                                                  offset,
                                                                  coverage)
            dbi.session.add(new_justification)
            dbi.session.add(new_justification_mapping_api)
        else:
            id = request_data['justification']['id']
            if len(dbi.session.query(ApiJustificationModel).filter(ApiJustificationModel.api_id == api.id).filter(
                    ApiJustificationModel.justification_id == id).filter(
                ApiJustificationModel.section == section).all()) > 0:
                dbi.engine.dispose()
                return "Justification already associated to the selected api Specification section.", 409

            existing_justification = dbi.session.query(JustificationModel).filter(JustificationModel.id == id).one()
            new_justification_mapping_api = ApiJustificationModel(api,
                                                                  existing_justification,
                                                                  section,
                                                                  offset,
                                                                  coverage)

            dbi.session.add(new_justification_mapping_api)

        dbi.session.commit()
        dbi.engine.dispose()
        return new_justification_mapping_api.as_dict()

    def put(self):
        request_data = request.get_json(force=True)

        if not check_fields_in_request(self.fields, request_data):
            return 'bad request!', 400

        dbi = db_orm.DbInterface()

        # Find api
        api = get_api_from_request(request_data, dbi.session)
        if not api:
            dbi.engine.dispose()
            return "Api not found", 404

        # check if api ...
        justification_mapping_api = dbi.session.query(ApiJustificationModel).filter(
            ApiJustificationModel.id == request_data["relation-id"]).one()
        justification = justification_mapping_api.justification

        # Update only modified fields
        if justification.description != request_data["justification"]["description"]:
            justification.description = request_data["justification"]["description"]

        if request_data['section'] != justification_mapping_api.section:
            justification_mapping_api.section = request_data["section"]

        if request_data['offset'] != justification_mapping_api.offset:
            justification_mapping_api.offset = request_data["offset"]

        if request_data['coverage'] != justification_mapping_api.coverage:
            justification_mapping_api.coverage = request_data["coverage"]

        dbi.session.commit()
        dbi.engine.dispose()
        return justification_mapping_api.as_dict()

    def delete(self):
        request_data = request.get_json(force=True)

        if not check_fields_in_request(['relation-id', 'api-id'], request_data):
            return 'bad request!', 400

        dbi = db_orm.DbInterface()

        # Find api
        api = get_api_from_request(request_data, dbi.session)
        if not api:
            dbi.engine.dispose()
            return "Api not found", 404

        # check if api ...
        justification_mapping_api = dbi.session.query(ApiJustificationModel).filter(
            ApiJustificationModel.id == request_data["relation-id"]).all()

        if len(justification_mapping_api) != 1:
            dbi.engine.dispose()
            return 'bad request!', 401

        justification_mapping_api = justification_mapping_api[0]

        if justification_mapping_api.api.id != api.id:
            dbi.engine.dispose()
            return 'bad request!', 401

        dbi.session.delete(justification_mapping_api)

        # TODO: Remove work item only user request to do
        """
        justification = justification_mapping_api.justification

        if len(dbi.session.query(ApiJustificationModel).filter( \
                ApiJustificationModel.api_id == api.id).filter( \
                ApiJustificationModel.justification_id == justification.id).all()) == 0:
            dbi.session.delete(justification)
        """

        dbi.session.commit()
        dbi.engine.dispose()
        return True


class ApiSwRequirementsMapping(Resource):
    fields = ['api-id', 'sw-requirement', 'section', 'coverage']

    def get(self):
        """
        curl <API_URL>/api/sw-requirements?api-id=<api-id>
        """
        args = get_query_string_args(request.args)
        if not check_fields_in_request(['api-id'], args):
            return 'bad request!', 400

        undesired_keys = ['section', 'offset']

        dbi = db_orm.DbInterface()

        # Find api
        api = get_api_from_request(args, dbi.session)
        if not api:
            dbi.engine.dispose()
            return "Api not found", 404

        ret = get_api_sw_requirements_mapping_sections(dbi, api)
        dbi.engine.dispose()
        return ret

    def post(self):
        request_data = request.get_json(force=True)

        if not check_fields_in_request(self.fields, request_data):
            return 'bad request!', 400

        dbi = db_orm.DbInterface()

        # Find api
        api = get_api_from_request(request_data, dbi.session)
        if not api:
            dbi.engine.dispose()
            return "Api not found", 404

        section = request_data['section']
        coverage = request_data['coverage']
        offset = request_data['offset']

        # Re using existing test case
        if 'id' not in request_data['sw-requirement'].keys():
            # Create a new one
            for check_field in SwRequirement.fields:
                if check_field.replace("_", "-") not in request_data['sw-requirement'].keys():
                    dbi.engine.dispose()
                    return "Bad request. Not consistent data.", 400

            title = request_data['sw-requirement']['title']
            description = request_data['sw-requirement']['description']

            if len(dbi.session.query(SwRequirementModel).filter(
                    SwRequirementModel.title == title).filter(
                SwRequirementModel.description == description).all()) > 0:
                dbi.engine.dispose()
                return "SW Requirement already associated to the selected api Specification section.", 409

            new_sw_requirement = SwRequirementModel(request_data['sw-requirement']['title'],
                                                    request_data['sw-requirement']['description'])
            new_sw_requirement_mapping_api = ApiSwRequirementModel(api,
                                                                   new_sw_requirement,
                                                                   section,
                                                                   offset,
                                                                   coverage)

            dbi.session.add(new_sw_requirement)
            dbi.session.add(new_sw_requirement_mapping_api)

        else:
            id = request_data['sw-requirement']['id']
            if len(dbi.session.query(ApiSwRequirementModel).filter(
                    ApiSwRequirementModel.api_id == api.id).filter(
                ApiSwRequirementModel.sw_requirement_id == id).filter(
                ApiSwRequirementModel.section == section).all()) > 0:
                dbi.engine.dispose()
                return "SW Requirement already associated to the selected api Specification section.", 409

            existing_sw_requirement = dbi.session.query(SwRequirementModel).filter(
                SwRequirementModel.id == id).one()

            new_sw_requirement_mapping_api = ApiSwRequirementModel(api,
                                                                   existing_sw_requirement,
                                                                   section,
                                                                   offset,
                                                                   coverage)
            dbi.session.add(new_sw_requirement_mapping_api)

        dbi.session.commit()
        dbi.engine.dispose()
        return new_sw_requirement_mapping_api.as_dict()

    def put(self):
        request_data = request.get_json(force=True)

        if not check_fields_in_request(self.fields, request_data):
            return 'bad request!', 400

        dbi = db_orm.DbInterface()

        # Find api
        api = get_api_from_request(request_data, dbi.session)
        if not api:
            dbi.engine.dispose()
            return "Api not found", 404

        sw_requirement_mapping_api = dbi.session.query(ApiSwRequirementModel).filter(
            ApiSwRequirementModel.id == request_data["relation-id"]).one()
        sw_requirement = sw_requirement_mapping_api.sw_requirement

        # Update only modified fields
        if sw_requirement.description != request_data["sw-requirement"]["description"]:
            sw_requirement.description = request_data["sw-requirement"]["description"]

        if sw_requirement.title != request_data["sw-requirement"]["title"]:
            sw_requirement.title = request_data["sw-requirement"]["title"]

        if sw_requirement_mapping_api.section != request_data["section"]:
            sw_requirement_mapping_api.section = request_data["section"]

        if sw_requirement_mapping_api.offset != request_data["offset"]:
            sw_requirement_mapping_api.offset = request_data["offset"]

        if sw_requirement_mapping_api.coverage != int(request_data["coverage"]):
            sw_requirement_mapping_api.coverage = int(request_data["coverage"])

        dbi.session.commit()
        dbi.engine.dispose()
        return sw_requirement_mapping_api.as_dict()

    def delete(self):
        request_data = request.get_json(force=True)

        if not check_fields_in_request(['relation-id', 'api-id'], request_data):
            return 'bad request!', 400

        dbi = db_orm.DbInterface()

        # Find api
        api = get_api_from_request(request_data, dbi.session)
        if not api:
            dbi.engine.dispose()
            return "Api not found", 404

        # check if api ...
        sw_requirement_mapping_api = dbi.session.query(ApiSwRequirementModel).filter(
            ApiSwRequirementModel.id == request_data["relation-id"]).one()
        if sw_requirement_mapping_api.api.id != api.id:
            dbi.engine.dispose()
            return 'bad request!', 401

        dbi.session.delete(sw_requirement_mapping_api)

        # TODO: Remove work item only user request to do
        """
        sw_requirement = sw_requirement_mapping_api.sw_requirement

        if len(dbi.session.query(ApiSwRequirementModel).filter( \
                ApiSwRequirementModel.api_id == api.id).filter( \
                ApiSwRequirementModel.sw_requirement_id == sw_requirement.id).all()) == 0:
            dbi.session.delete(sw_requirement)
        """

        dbi.session.commit()
        dbi.engine.dispose()
        return True


class Justification(Resource):
    fields = ['description']

    def get(self):
        """
        """
        args = get_query_string_args(request.args)
        dbi = db_orm.DbInterface()
        query = dbi.session.query(JustificationModel)

        if "join" in args.keys() and "join_id" in args.keys():
            if args["join"] == JOIN_APIS_TABLE:
                query = query.join(ApiModel).filter(ApiModel.id == args["join_id"])

        filter_by_id = False
        for arg_key in args.keys():
            if "field" in arg_key:
                field_n = arg_key.replace('field', '')
                field = args[f'field{field_n}']
                filter = args[f'filter{field_n}']
                if field == 'id':
                    filter_by_id = True
                    break
        if filter_by_id:
            query = query.filter(JustificationModel.id == filter)
            dbi.engine.dispose()
            return [ju.as_dict() for ju in query.all()]

        for arg_key in args.keys():
            if "field" in arg_key:
                field_n = arg_key.replace('field', '')
                field = args[f'field{field_n}']
                filter = args[f'filter{field_n}']
                if field == 'description':
                    query = query.filter(JustificationModel.description.like(f'%{filter}%'))

            if arg_key == "search":
                query = query.filter(JustificationModel.description.like(f'%{args["search"]}%'))

        jus = [ju.as_dict() for ju in query.all()]

        if 'mode' in args.keys():
            if args['mode'] == 'minimal':
                minimal_keys = ['id', 'description']
                jus = [{key: val for key, val in sub.items() if key in minimal_keys} for sub in jus]

        dbi.engine.dispose()
        return jus


class TestSpecification(Resource):
    fields = ['title', 'preconditions', 'test_description', 'expected_behavior']

    def get(self):
        """
        """
        args = get_query_string_args(request.args)
        dbi = db_orm.DbInterface()

        if "join" in args.keys() and "join_id" in args.keys():
            if args["join"] == JOIN_APIS_TABLE:
                join_test_specs = dbi.session.query(ApiTestSpecificationModel).filter(
                    ApiTestSpecificationModel.api_id == args["join_id"]).all()
                join_test_specs = [x.id for x in join_test_specs]
                query = dbi.session.query(TestSpecificationModel).filter(
                    TestSpecificationModel.id.in_(join_test_specs))
            elif args["join"] == JOIN_SW_REQUIREMENTS_TABLE:
                join_test_specs = dbi.session.query(SwRequirementTestSpecificationModel).filter(
                    SwRequirementTestSpecificationModel.sw_requirement_id == args["join_id"]).all()
                join_test_specs = [x.id for x in join_test_specs]
                query = dbi.session.query(TestSpecificationModel).filter(
                    TestSpecificationModel.id.in_(join_test_specs))
        else:
            query = dbi.session.query(TestSpecificationModel)

        filter_by_id = False
        for arg_key in args.keys():
            if "field" in arg_key:
                field_n = arg_key.replace('field', '')
                field = args[f'field{field_n}']
                filter = args[f'filter{field_n}']
                if field == 'id':
                    filter_by_id = True
                    break
        if filter_by_id:
            query = query.filter(TestSpecificationModel.id == filter)
            dbi.engine.dispose()
            return [ts.as_dict() for ts in query.all()]

        for arg_key in args.keys():
            if "field" in arg_key:
                field_n = arg_key.replace('field', '')
                field = args[f'field{field_n}']
                filter = args[f'filter{field_n}']
                if field == 'title':
                    query = query.filter(TestSpecificationModel.title.like(f'%{filter}%'))
                elif field == 'preconditions':
                    query = query.filter(TestSpecificationModel.preconditions.like(f'%{filter}%'))
                elif field == 'test-description':
                    query = query.filter(TestSpecificationModel.test_description.like(f'%{filter}%'))
                elif field == 'expected-description':
                    query = query.filter(TestSpecificationModel.expected_behavior.like(f'%{filter}%'))

            if arg_key == "search":
                query = query.filter(or_(TestSpecificationModel.title.like(f'%{args["search"]}%'),
                                         TestSpecificationModel.preconditions.like(f'%{args["search"]}%'),
                                         TestSpecificationModel.test_description.like(f'%{args["search"]}%'),
                                         TestSpecificationModel.expected_behavior.like(f'%{args["search"]}%')
                                         ))

        tss = [ts.as_dict() for ts in query.all()]

        if 'mode' in args.keys():
            if args['mode'] == 'minimal':
                minimal_keys = ['id', 'title']
                tss = [{key: val for key, val in sub.items() if key in minimal_keys} for sub in tss]

        dbi.engine.dispose()
        return tss


class SwRequirement(Resource):
    fields = ["title", "description"]

    def get(self):
        """
        """
        args = get_query_string_args(request.args)
        dbi = db_orm.DbInterface()

        if "join" in args.keys() and "join_id" in args.keys():
            if args["join"] == JOIN_APIS_TABLE:
                # TODO Fix the join table
                # Api and SwRequirement are not related
                api_sw_requirements = dbi.session.query(ApiSwRequirementModel).filter(
                    ApiSwRequirementModel.api_id == args["join_id"]).all()
                api_sw_requirement_ids = [x.id for x in api_sw_requirements]
                query = dbi.session.query(SwRequirementModel).filter(
                    SwRequirementModel.id.in_(api_sw_requirement_ids))
            else:
                dbi.engine.dispose()
                return []
        else:
            query = dbi.session.query(SwRequirementModel)

        filter_by_id = False
        for arg_key in args.keys():
            if "field" in arg_key:
                field_n = arg_key.replace('field', '')
                field = args[f'field{field_n}']
                filter = args[f'filter{field_n}']
                if field == 'id':
                    filter_by_id = True
                    break

        if filter_by_id:
            query = query.filter(SwRequirementModel.id == filter)
            dbi.engine.dispose()
            return [sr.as_dict() for sr in query.all()]

        for arg_key in args.keys():
            if "field" in arg_key:
                field_n = arg_key.replace('field', '')
                field = args[f'field{field_n}']
                filter = args[f'filter{field_n}']
                if field == 'title':
                    query = query.filter(SwRequirementModel.title.like(f'%{filter}%'))
                elif field == 'description':
                    query = query.filter(SwRequirementModel.description.like(f'%{filter}%'))

            if arg_key == "search":
                query = query.filter(or_(SwRequirementModel.title.like(f'%{args["search"]}%'),
                                         SwRequirementModel.description.like(f'%{args["search"]}%')
                                         ))

        srs = [sr.as_dict() for sr in query.all()]

        if 'mode' in args.keys():
            if args['mode'] == 'minimal':
                minimal_keys = ['id', 'title']
                srs = [{key: val for key, val in sub.items() if key in minimal_keys} for sub in srs]

        dbi.engine.dispose()
        return srs


class TestCase(Resource):
    fields = ['title', 'description', 'repository', 'relative_path']

    def get(self):
        """
        """
        args = get_query_string_args(request.args)
        dbi = db_orm.DbInterface()

        if "join" in args.keys() and "join_id" in args.keys():
            if args["join"] == JOIN_APIS_TABLE:
                join_test_cases = dbi.session.query(ApiTestCaseModel).filter(
                    ApiTestCaseModel.api_id == args["join_id"]).all()
                join_test_cases_ids = [x.id for x in join_test_cases]
                query = dbi.session.query(TestCaseModel).filter(TestCaseModel.id.in_(join_test_cases_ids))
            elif args["join"] == JOIN_SW_REQUIREMENTS_TABLE:
                join_test_cases = dbi.session.query(ApiTestCaseModel).filter(
                    ApiTestCaseModel.api_id == args["join_id"]).all()
                join_test_cases_ids = [x.id for x in join_test_cases]
                query = dbi.session.query(TestCaseModel).filter(TestCaseModel.id.in_(join_test_cases_ids))
            elif args["join"] == JOIN_TEST_SPECIFICATIONS_TABLE:
                join_test_cases = dbi.session.query(ApiTestCaseModel).filter(
                    ApiTestCaseModel.api_id == args["join_id"]).all()
                join_test_cases_ids = [x.id for x in join_test_cases]
                query = dbi.session.query(TestCaseModel).filter(TestCaseModel.id.in_(join_test_cases_ids))
        else:
            query = dbi.session.query(TestCaseModel)

        filter_by_id = False
        for arg_key in args.keys():
            if "field" in arg_key:
                field_n = arg_key.replace('field', '')
                field = args[f'field{field_n}']
                filter = args[f'filter{field_n}']
                if field == 'id':
                    filter_by_id = True
                    break
        if filter_by_id:
            query = query.filter(TestCaseModel.id == filter)
            dbi.engine.dispose()
            return [tc.as_dict() for tc in query.all()]

        for arg_key in args.keys():
            if "field" in arg_key:
                field_n = arg_key.replace('field', '')
                field = args[f'field{field_n}']
                filter = args[f'filter{field_n}']
                if field == 'title':
                    query = query.filter(TestCaseModel.title.like(f'%{filter}%'))
                elif field == 'description':
                    query = query.filter(TestCaseModel.description.like(f'%{filter}%'))
                elif field == 'repository':
                    query = query.filter(TestCaseModel.repository.like(f'%{filter}%'))
                elif field == 'relative-path':
                    query = query.filter(TestCaseModel.relative_path.like(f'%{filter}%'))

            if arg_key == "search":
                query = query.filter(or_(TestCaseModel.title.like(f'%{args["search"]}%'),
                                         TestCaseModel.description.like(f'%{args["search"]}%'),
                                         TestCaseModel.repository.like(f'%{args["search"]}%'),
                                         TestCaseModel.relative_path.like(f'%{args["search"]}%')
                                         ))

        tcs = [tc.as_dict() for tc in query.all()]

        if 'mode' in args.keys():
            if args['mode'] == 'minimal':
                minimal_keys = ['id', 'title']
                tcs = [{key: val for key, val in sub.items() if key in minimal_keys} for sub in tcs]

        dbi.engine.dispose()
        return tcs


class SwRequirementTestSpecificationsMapping(Resource):
    fields = ['api-id', 'sw-requirement', 'test-specification', 'coverage']

    def get(self):
        """
        curl http://localhost:5000/api/test-specifications?db=head&field=id&filter=24
        """

        ret = {}
        return ret

    def post(self):
        request_data = request.get_json(force=True)

        mandatory_fields = self.fields + ['relation-id']
        if not check_fields_in_request(mandatory_fields, request_data):
            return 'bad request!', 400

        if 'id' not in request_data['sw-requirement'].keys():
            return 'bad request!!', 400

        dbi = db_orm.DbInterface()
        sw_requirement_id = request_data['sw-requirement']['id']
        coverage = request_data['coverage']

        try:
            sw_requirement = dbi.session.query(SwRequirementModel).filter(
                SwRequirementModel.id == sw_requirement_id).one()
        except:
            dbi.engine.dispose()
            return "Sw Requirement not found", 400

        # Find ApiModel
        api = get_api_from_request(request_data, dbi.session)
        if not api:
            dbi.engine.dispose()
            return "Api not found", 404

        # Find ApiSwRequirementModel
        sr_api = None
        srs_api = dbi.session.query(ApiSwRequirementModel).filter(
            ApiSwRequirementModel.id == request_data['relation-id']).all()
        if len(srs_api) != 1:
            dbi.engine.dispose()
            return "Api not found", 404
        else:
            sr_api = srs_api[0]

        if 'id' not in request_data['test-specification'].keys():
            # Create a new one
            for check_field in TestSpecification.fields:
                if check_field.replace("_", "-") not in request_data['test-specification'].keys():
                    dbi.engine.dispose()
                    return "Bad request. Not consistent data.", 400

            title = request_data['test-specification']['title']
            preconditions = request_data['test-specification']['preconditions']
            test_description = request_data['test-specification']['test-description']
            expected_behavior = request_data['test-specification']['expected-behavior']

            existing_test_specifications = dbi.session.query(TestSpecificationModel).filter(
                TestSpecificationModel.title == title).filter(
                TestSpecificationModel.preconditions == preconditions).filter(
                TestSpecificationModel.test_description == test_description).filter(
                TestSpecificationModel.expected_behavior == expected_behavior).all()

            for ts in existing_test_specifications:
                ts_mapping = dbi.session.query(SwRequirementTestSpecificationModel).join(
                    ApiSwRequirementModel).filter(
                    ApiSwRequirementModel.sw_requirement_id == sw_requirement_id).filter(
                    SwRequirementTestSpecificationModel.test_specification_id == ts.id).filter(
                    SwRequirementTestSpecificationModel.api_id == api.id).all()
                if len(ts_mapping) > 0:
                    dbi.engine.dispose()
                    return "Test Specification already associated to the selected api Specification section.", 409

            new_test_specification = TestSpecificationModel(title,
                                                            preconditions,
                                                            test_description,
                                                            expected_behavior)

            new_test_specification_mapping_sw_requirement = SwRequirementTestSpecificationModel(sr_api,
                                                                                                new_test_specification,
                                                                                                coverage)

            dbi.session.add(new_test_specification)
            dbi.session.add(new_test_specification_mapping_sw_requirement)

        else:
            test_specification_id = request_data['test-specification']['id']

            if len(dbi.session.query(SwRequirementTestSpecificationModel).filter(
                    SwRequirementTestSpecificationModel.sw_requirement_mapping_api_id == request_data[
                        'relation-id']).filter(
                SwRequirementTestSpecificationModel.test_specification_id == test_specification_id).all()) > 0:
                dbi.engine.dispose()
                return "Test Specification already associated to the selected Api and Sw Requirement.", 409

            try:
                test_specification = dbi.session.query(TestSpecificationModel).filter(
                    TestSpecificationModel.id == test_specification_id).one()
            except:
                return "Unable to find the selected Test Specification", 400

            if not isinstance(test_specification, TestSpecificationModel):
                dbi.engine.dispose()
                return "Bad request.", 400

            new_test_specification_mapping_sw_requirement = SwRequirementTestSpecificationModel(sr_api,
                                                                                                test_specification,
                                                                                                coverage)
            dbi.session.add(new_test_specification_mapping_sw_requirement)

        dbi.session.commit()
        dbi.engine.dispose()
        return new_test_specification_mapping_sw_requirement.as_dict()

    def put(self):

        request_data = request.get_json(force=True)

        mandatory_fields = self.fields + ['relation-id']
        if not check_fields_in_request(mandatory_fields, request_data):
            return 'bad request!', 400

        dbi = db_orm.DbInterface()

        sw_mapping_ts = dbi.session.query(SwRequirementTestSpecificationModel).filter(
            SwRequirementTestSpecificationModel.id == request_data['relation-id']
        ).one()

        test_specification = sw_mapping_ts.test_specification

        # Update only modified fields
        if test_specification.title != request_data["test-specification"]["title"]:
            test_specification.title = request_data["test-specification"]["title"]

        if test_specification.preconditions != request_data["test-specification"]["preconditions"]:
            test_specification.preconditions = request_data["test-specification"]["preconditions"]

        if test_specification.test_description != request_data["test-specification"]["test-description"]:
            test_specification.test_description = request_data["test-specification"]["test-description"]

        if test_specification.expected_behavior != request_data["test-specification"]["expected-behavior"]:
            test_specification.expected_behavior = request_data["test-specification"]["expected-behavior"]

        if sw_mapping_ts.coverage != int(request_data["coverage"]):
            sw_mapping_ts.coverage = int(request_data["coverage"])

        ret = sw_mapping_ts.as_dict(db_session=dbi.session)
        dbi.session.commit()
        dbi.engine.dispose()
        return ret

    def delete(self):

        ret = False
        request_data = request.get_json(force=True)

        mandatory_fields = ['relation-id']
        if not check_fields_in_request(mandatory_fields, request_data):
            return 'bad request!', 400

        dbi = db_orm.DbInterface()

        sw_mapping_ts = dbi.session.query(SwRequirementTestSpecificationModel).filter(
            SwRequirementTestSpecificationModel.id == request_data['relation-id']
        ).one()

        # test_specification = sw_mapping_ts.test_specification
        # dbi.session.delete(test_specification)

        dbi.session.delete(sw_mapping_ts)
        dbi.session.commit()
        dbi.engine.dispose()

        return ret


class SwRequirementTestCasesMapping(Resource):
    fields = ['api-id', 'sw-requirement', 'test-case', 'coverage']

    def get(self):
        """
        curl http://localhost:5000/api/test-specifications?db=head&field=id&filter=24
        """

        ret = {}
        return ret

    def post(self):
        request_data = request.get_json(force=True)

        post_mandatory_fields = self.fields + ['relation-id']
        if not check_fields_in_request(post_mandatory_fields, request_data):
            return 'bad request!', 400

        if 'id' not in request_data['sw-requirement'].keys():
            return 'bad request!!', 400

        relation_id = request_data['relation-id']
        dbi = db_orm.DbInterface()

        # Find api
        api = get_api_from_request(request_data, dbi.session)
        if not api:
            dbi.engine.dispose()
            return "Api not found", 404

        # Find ApiSwRequirement
        api_sr_query = dbi.session.query(ApiSwRequirementModel).filter(
            ApiSwRequirementModel.id == relation_id
        )
        api_sr_list = api_sr_query.all()
        if len(api_sr_list) != 1:
            dbi.engine.dispose()
            return "Api not found", 404
        else:
            api_sr = api_sr_list[0]

        sw_requirement_id = request_data['sw-requirement']['id']
        coverage = request_data['coverage']

        try:
            sw_requirement = dbi.session.query(SwRequirementModel).filter(
                SwRequirementModel.id == sw_requirement_id).one()
        except:
            dbi.engine.dispose()
            return "Sw Requirement not found", 400

        if 'id' not in request_data['test-case'].keys():
            # Create a new one
            for check_field in TestCase.fields:
                if check_field.replace("_", "-") not in request_data['test-case'].keys():
                    dbi.engine.dispose()
                    return "Bad request. Not consistent data.", 400

            title = request_data['test-case']['title']
            description = request_data['test-case']['description']
            repository = request_data['test-case']['repository']
            relative_path = request_data['test-case']['relative-path']

            existing_test_cases = dbi.session.query(TestCaseModel).filter(
                TestCaseModel.title == title).filter(
                TestCaseModel.description == description).filter(
                TestCaseModel.repository == repository).filter(
                TestCaseModel.relative_path == relative_path).all()

            for tc in existing_test_cases:
                tc_mapping = dbi.session.query(SwRequirementTestCaseModel).filter(
                    SwRequirementTestCaseModel.id == relation_id).filter(
                    SwRequirementTestCaseModel.test_case_id == tc.id).all()
                if len(tc_mapping) > 0:
                    dbi.engine.dispose()
                    return "Test Case already associated to the selected api Specification section.", 409

            new_test_case = TestCaseModel(repository, relative_path, title, description)

            new_test_case_mapping_sw_requirement = SwRequirementTestCaseModel(api_sr,
                                                                              new_test_case,
                                                                              coverage)

            dbi.session.add(new_test_case)
            dbi.session.add(new_test_case_mapping_sw_requirement)

        else:
            # Map an existing Test Case
            test_case_id = request_data['test-case']['id']

            if len(dbi.session.query(SwRequirementTestCaseModel).filter(
                    SwRequirementTestCaseModel.id == relation_id).filter(
                SwRequirementTestCaseModel.test_case_id == test_case_id).all()) > 0:
                dbi.engine.dispose()
                return "Test Case already associated to the selected Api and Sw Requirement.", 409

            try:
                test_case = dbi.session.query(TestCaseModel).filter(
                    TestCaseModel.id == test_case_id).one()
            except:
                dbi.engine.dispose()
                return "Bad request.", 400

            if not isinstance(test_case, TestCaseModel):
                dbi.engine.dispose()
                return "Bad request.", 400

            new_test_case_mapping_sw_requirement = SwRequirementTestCaseModel(api_sr,
                                                                              test_case,
                                                                              coverage)
            dbi.session.add(new_test_case_mapping_sw_requirement)

        dbi.session.commit()
        dbi.engine.dispose()
        return new_test_case_mapping_sw_requirement.as_dict()

    def put(self):
        request_data = request.get_json(force=True)

        mandatory_fields = self.fields + ['relation-id']
        if not check_fields_in_request(mandatory_fields, request_data):
            return 'bad request!', 400

        dbi = db_orm.DbInterface()

        sw_mapping_tc = dbi.session.query(SwRequirementTestCaseModel).filter(
            SwRequirementTestCaseModel.id == request_data['relation-id']
        ).one()

        test_case = sw_mapping_tc.test_case

        # Update only modified fields
        if test_case.title != request_data["test-case"]["title"]:
            test_case.title = request_data["test-case"]["title"]

        if test_case.description != request_data["test-case"]["description"]:
            test_case.description = request_data["test-case"]["description"]

        if test_case.repository != request_data["test-case"]["repository"]:
            test_case.repository = request_data["test-case"]["repository"]

        if test_case.relative_path != request_data["test-case"]["relative-path"]:
            test_case.relative_path = request_data["test-case"]["relative-path"]

        if sw_mapping_tc.coverage != int(request_data["coverage"]):
            sw_mapping_tc.coverage = int(request_data["coverage"])

        ret = sw_mapping_tc.as_dict(db_session=dbi.session)
        dbi.session.commit()
        dbi.engine.dispose()
        return ret

    def delete(self):

        ret = False
        request_data = request.get_json(force=True)

        mandatory_fields = ['relation-id']
        if not check_fields_in_request(mandatory_fields, request_data):
            return 'bad request!', 400

        dbi = db_orm.DbInterface()

        sw_mapping_tc = dbi.session.query(SwRequirementTestCaseModel).filter(
            SwRequirementTestCaseModel.id == request_data['relation-id']
        ).one()

        # test_case = sw_mapping_tc.test_case
        # dbi.session.delete(test_case)

        dbi.session.delete(sw_mapping_tc)
        dbi.session.commit()
        dbi.engine.dispose()

        return ret


class TestSpecificationTestCasesMapping(Resource):
    fields = ['api-id', 'test-specification', 'test-case', 'coverage']

    def get(self):
        return []

    def post(self):
        request_data = request.get_json(force=True)
        api_ts = None
        sr_ts = None

        post_mandatory_fields = self.fields + ['relation-id', 'relation-to']
        if not check_fields_in_request(post_mandatory_fields, request_data):
            return 'bad request!', 400

        if 'id' not in request_data['test-specification'].keys():
            return 'bad request!!', 400

        relation_id = request_data['relation-id']
        dbi = db_orm.DbInterface()

        # Find api
        api = get_api_from_request(request_data, dbi.session)
        if not api:
            dbi.engine.dispose()
            return "Api not found", 404

        # Find ApiSwRequirement
        if request_data['relation-to'] == 'api':
            relation_to_query = dbi.session.query(ApiTestSpecificationModel).filter(
                ApiTestSpecificationModel.id == relation_id
            )
        elif request_data['relation-to'] == 'sw-requirement':
            relation_to_query = dbi.session.query(SwRequirementTestSpecificationModel).filter(
                SwRequirementTestSpecificationModel.id == relation_id
            )
        else:
            dbi.engine.dispose()
            return "Bad request!!!", 400

        relation_to_list = relation_to_query.all()
        if len(relation_to_list) != 1:
            dbi.engine.dispose()
            return "Parent mapping not found", 404
        else:
            relation_to_item = relation_to_list[0]

        if request_data['relation-to'] == 'api':
            api_ts = relation_to_item
        elif request_data['relation-to'] == 'sw-requirement':
            sr_ts = relation_to_item

        test_specification_id = request_data['test-specification']['id']
        coverage = request_data['coverage']

        try:
            test_specification = dbi.session.query(TestSpecificationModel).filter(
                TestSpecificationModel.id == test_specification_id).one()
        except:
            dbi.engine.dispose()
            return "Test Specification not found", 400

        if 'id' not in request_data['test-case'].keys():
            # Create a new one
            for check_field in TestCase.fields:
                if check_field.replace("_", "-") not in request_data['test-case'].keys():
                    dbi.engine.dispose()
                    return "Bad request. Not consistent data.", 400

            title = request_data['test-case']['title']
            description = request_data['test-case']['description']
            repository = request_data['test-case']['repository']
            relative_path = request_data['test-case']['relative-path']

            existing_test_cases = dbi.session.query(TestCaseModel).filter(
                TestCaseModel.title == title).filter(
                TestCaseModel.description == description).filter(
                TestCaseModel.repository == repository).filter(
                TestCaseModel.relative_path == relative_path).all()

            for tc in existing_test_cases:
                tc_mapping = dbi.session.query(TestSpecificationTestCaseModel).filter(
                    TestSpecificationTestCaseModel.id == relation_id).filter(
                    TestSpecificationTestCaseModel.test_case_id == tc.id).all()
                if len(tc_mapping) > 0:
                    dbi.engine.dispose()
                    return "Test Case already associated to the selected api Specification section.", 409

            new_test_case = TestCaseModel(repository, relative_path, title, description)

            new_test_case_mapping_test_specification = TestSpecificationTestCaseModel(api_ts,
                                                                                      sr_ts,
                                                                                      new_test_case,
                                                                                      coverage)

            dbi.session.add(new_test_case)
            dbi.session.add(new_test_case_mapping_test_specification)

        else:
            # Map an existing Test Case
            test_case_id = request_data['test-case']['id']

            if len(dbi.session.query(TestSpecificationTestCaseModel).filter(
                    TestSpecificationTestCaseModel.id == relation_id).filter(
                TestSpecificationTestCaseModel.test_case_id == test_case_id).all()) > 0:
                dbi.engine.dispose()
                return "Test Case already associated to the selected Api and Test Specification.", 409

            try:
                test_case = dbi.session.query(TestCaseModel).filter(
                    TestCaseModel.id == test_case_id).one()
            except:
                dbi.engine.dispose()
                return "Bad request.", 400

            if not isinstance(test_case, TestCaseModel):
                dbi.engine.dispose()
                return "Bad request.", 400

            new_test_case_mapping_test_specification = TestSpecificationTestCaseModel(api_ts,
                                                                                      sr_ts,
                                                                                      test_case,
                                                                                      coverage)
            dbi.session.add(new_test_case_mapping_test_specification)

        dbi.session.commit()
        dbi.engine.dispose()
        return new_test_case_mapping_test_specification.as_dict()

    def put(self):
        request_data = request.get_json(force=True)

        mandatory_fields = self.fields + ['relation-id']
        if not check_fields_in_request(mandatory_fields, request_data):
            return 'bad request!', 400

        dbi = db_orm.DbInterface()

        ts_mapping_tc = dbi.session.query(TestSpecificationTestCaseModel).filter(
            TestSpecificationTestCaseModel.id == request_data['relation-id']
        ).one()

        test_case = ts_mapping_tc.test_case

        # Update only modified fields
        if test_case.title != request_data["test-case"]["title"]:
            test_case.title = request_data["test-case"]["title"]

        if test_case.description != request_data["test-case"]["description"]:
            test_case.description = request_data["test-case"]["description"]

        if test_case.repository != request_data["test-case"]["repository"]:
            test_case.repository = request_data["test-case"]["repository"]

        if test_case.relative_path != request_data["test-case"]["relative-path"]:
            test_case.relative_path = request_data["test-case"]["relative-path"]

        if ts_mapping_tc.coverage != int(request_data["coverage"]):
            ts_mapping_tc.coverage = int(request_data["coverage"])

        ret = ts_mapping_tc.as_dict(db_session=dbi.session)
        dbi.session.commit()
        dbi.engine.dispose()
        return ret

    def delete(self):
        ret = False
        request_data = request.get_json(force=True)

        mandatory_fields = ['relation-id']
        if not check_fields_in_request(mandatory_fields, request_data):
            return 'bad request!', 400

        dbi = db_orm.DbInterface()

        ts_mapping_tc = dbi.session.query(TestSpecificationTestCaseModel).filter(
            TestSpecificationTestCaseModel.id == request_data['relation-id']
        ).one()

        # test_case = ts_mapping_tc.test_case
        # dbi.session.delete(test_case)

        dbi.session.delete(ts_mapping_tc)
        dbi.session.commit()
        dbi.engine.dispose()

        return ret


class ForkApiSwRequirement(Resource):
    def post(self):
        ret = False
        request_data = request.get_json(force=True)

        mandatory_fields = ['relation-id']
        if not check_fields_in_request(mandatory_fields, request_data):
            return 'bad request!', 400

        dbi = db_orm.DbInterface()

        try:
            asr_mapping = dbi.session.query(ApiSwRequirementModel).filter(
                ApiSwRequirementModel.id == request_data['relation-id']
            ).one()
        except:
            return 'bad request!!!', 400

        new_sr = SwRequirementModel(asr_mapping.sw_requirement.title,
                                    asr_mapping.sw_requirement.description)
        dbi.session.add(new_sr)
        dbi.session.commit()

        asr_mapping.sw_requirement_id = new_sr.id

        dbi.session.commit()
        dbi.engine.dispose()
        return asr_mapping.as_dict()


api.add_resource(Api, '/apis')
api.add_resource(ApiHistory, '/apis/history')
api.add_resource(ApiSpecification, '/api-specifications')
api.add_resource(Library, '/libraries')
api.add_resource(SPDXLibrary, '/spdx/libraries')
api.add_resource(Justification, '/justifications')
api.add_resource(SwRequirement, '/sw-requirements')
api.add_resource(TestSpecification, '/test-specifications')
api.add_resource(TestCase, '/test-cases')
# Mapping
# - Direct
api.add_resource(ApiSpecificationsMapping, '/mapping/api/specifications')
api.add_resource(ApiJustificationsMapping, '/mapping/api/justifications')
api.add_resource(ApiSwRequirementsMapping, '/mapping/api/sw-requirements')
api.add_resource(ApiTestSpecificationsMapping, '/mapping/api/test-specifications')
api.add_resource(ApiTestCasesMapping, '/mapping/api/test-cases')
# - Indirect
api.add_resource(SwRequirementTestSpecificationsMapping, '/mapping/sw-requirement/test-specifications')
api.add_resource(SwRequirementTestCasesMapping, '/mapping/sw-requirement/test-cases')
api.add_resource(TestSpecificationTestCasesMapping, '/mapping/test-specification/test-cases')
# History
api.add_resource(MappingHistory, '/mapping/history')
api.add_resource(CheckSpecification, '/apis/check-specification')
api.add_resource(FixNewSpecificationWarnings, '/apis/fix-specification-warnings')

# Usage
api.add_resource(MappingUsage, '/mapping/usage')
# Comments
api.add_resource(Comment, '/comments')
# Fork
api.add_resource(ForkApiSwRequirement, '/fork/api/sw-requirement')
# api.add_resource(ForkTestSpecification, '/fork/api/test-specification')
# api.add_resource(ForkTestCase, '/fork/api/test-case')
# api.add_resource(ForkJustification, '/fork/api/justification')

if __name__ == "__main__":
    import api_url

    # app.config['SECRET_KEY'] = os.environ["app_token"]
    app.config['ENV'] = 'local'
    app.run(host='0.0.0.0', port=api_url.api_port)
