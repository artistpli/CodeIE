#!/usr/bin/env python
# -*- coding:utf-8 -*-
from collections import defaultdict, OrderedDict
import os
from uie.extraction.record_schema import RecordSchema
from uie.extraction.predict_parser import get_predict_parser
from uie.sel2record.record import EntityRecord, MapConfig, RelationRecord, EventRecord
import logging

logger = logging.getLogger("__main__")


task_record_map = {
    'entity': EntityRecord,
    'relation': RelationRecord,
    'event': EventRecord,
}


def proprocessing_graph_record(graph, schema_dict):
    """ Mapping generated spot-asoc result to Entity/Relation/Event
    将抽取的Spot-Asoc结构，根据不同的 Schema 转换成 Entity/Relation/Event 结果
    """
    records = {
        'entity': list(),
        'relation': list(),
        'event': list(),
    }

    entity_dict = OrderedDict()

    # 根据不同任务的 Schema 将不同的 Spot 对应到不同抽取结果： Entity/Event
    # Mapping generated spot result to Entity/Event
    for record in graph['pred_record']:

        if record['type'] in schema_dict['entity'].type_list:
            records['entity'] += [{
                'text': record['spot'],
                'type': record['type']
            }]
            entity_dict[record['spot']] = record['type']

        elif record['type'] in schema_dict['event'].type_list:
            records['event'] += [{
                'trigger': record['spot'],
                'type': record['type'],
                'roles': record['asocs']
            }]

        else:
            print("Type `%s` invalid." % record['type'])

    # 根据不同任务的 Schema 将不同的 Asoc 对应到不同抽取结果： Relation/Argument
    # Mapping generated asoc result to Relation/Argument
    for record in graph['pred_record']:
        if record['type'] in schema_dict['entity'].type_list:
            for role in record['asocs']:
                records['relation'] += [{
                    'type': role[0],
                    'roles': [
                        (record['type'], record['spot']),
                        (entity_dict.get(role[1], record['type']), role[1]),
                    ]
                }]

    if len(entity_dict) > 0:
        for record in records['event']:
            if record['type'] in schema_dict['event'].type_list:
                new_role_list = list()
                for role in record['roles']:
                    if role[1] in entity_dict:
                        new_role_list += [role]
                record['roles'] = new_role_list

    return records


class SEL2Record:
    def __init__(self, schema_dict, decoding_schema, map_config: MapConfig) -> None:
        self._schema_dict = schema_dict
        self._predict_parser = get_predict_parser(
            decoding_schema=decoding_schema,
            label_constraint=schema_dict['record']
        )
        self._map_config = map_config

    def __repr__(self) -> str:
        return f"## {self._map_config}"

    def sel2record(self, pred, text, tokens):
        # Parsing generated SEL to String-level Record
        # 将生成的结构表达式解析成 String 级别的 Record
        well_formed_list, counter = self._predict_parser.decode(
            gold_list=[],
            pred_list=[pred],
            text_list=[text],
        )

        # Convert String-level Record to Entity/Relation/Event
        # 将抽取的 Spot-Asoc Record 结构
        # 根据不同的 Schema 转换成 Entity/Relation/Event 结果
        pred_records = proprocessing_graph_record(
            well_formed_list[0],
            self._schema_dict
        )

        pred = defaultdict(dict)
        pred['statistic']['ill-formed'] = False
        pred['statistic']['Invalid-Label'] = False
        pred['statistic']['Invalid-Text-Span'] = False
        pred['statistic']['Invalid-Label-asoc'] = False
        pred['statistic']['Invalid-Text-Span-asoc'] =False

        if 'ill-formed' in counter:
            pred['statistic']['ill-formed'] = True
        if 'Invalid-Label' in counter:
            pred['statistic']['Invalid-Label'] = True
        if 'Invalid-Text-Span' in counter:
            pred['statistic']['Invalid-Text-Span'] = True
        if 'Invalid-Label-asoc' in counter:
            print ("Invalid-Label-asoc")
            print (pred)
            exit(0)
            pred['statistic']['Invalid-Label-asoc'] = True
        if 'Invalid-Text-Span-asoc' in counter:
            pred['statistic']['Invalid-Text-Span-asoc'] = True

        # Mapping String-level record to Offset-level record
        # 将 String 级别的 Record 回标成 Offset 级别的 Record
        for task in task_record_map:
            record_map = task_record_map[task](
                map_config=self._map_config,
            )

            pred[task]['offset'] = record_map.to_offset(
                instance=pred_records.get(task, []),
                tokens=tokens,
            )

            pred[task]['string'] = record_map.to_string(
                pred_records.get(task, []),
            )
        return pred

    @staticmethod
    def load_schema_dict(schema_folder):
        schema_dict = dict()
        for schema_key in ['record', 'entity', 'relation', 'event']:
            schema_filename = os.path.join(schema_folder, f'{schema_key}.schema')
            if os.path.exists(schema_filename):
                schema_dict[schema_key] = RecordSchema.read_from_file(
                    schema_filename
                )
            else:
                logger.warning(f"{schema_filename} is empty, ignore.")
                schema_dict[schema_key] = RecordSchema.get_empty_schema()
        return schema_dict