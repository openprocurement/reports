import os
import csv
from reports.core import BaseUtility, NEW_ALG_DATE
from reports.helpers import (
    value_currency_normalize,
    get_arguments_parser,
    prepare_result_file_name,
    Kind
)


HEADERS = [
    "tender", "tenderID", "lot",
    "status", "lot_status", "currency",
    "kind", "value", "rate", "bill"
]


class TendersUtility(BaseUtility):

    headers = HEADERS
    view = 'report/tenders_owner_date'

    def __init__(
            self, broker, period, config,
            timezone="Europe/Kiev",
            ):
        super(TendersUtility, self).__init__(
            broker, period, config, operation="tenders", timezone=timezone)

        # TODO:
        # [self.headers.remove(col) for col in self.skip_cols if col in self.headers]

    def row(self, record):
        rate = None
        tender = record.get('tender', '')
        date = record.get('startdate', '')
        if date < self.threshold_date:
            version = 1
        elif date > NEW_ALG_DATE:
            version = 3
        else:
            version = 2
        if record.get('kind') not in self.kinds and version != 3:
            self.Logger.info('Skip tender {} by kind'.format(tender))
            return '', ''
        row = list(record.get(col, '') for col in self.headers[:-2])
        value, rate = self.convert_value(record)
        r = str(rate) if rate else ''
        row.append(r)
        grid = 2017 if record.get('startdate', '') < self.threshold_date else 2016
        row.append(self.get_payment(value, grid))
        self.Logger.info(
            "Refund {} for tender {} with value {}".format(
                row[-1], row[0], value
            )
        )
        return row, version

    def write_csv(self):
        is_added = False
        second_version = []
        new_version = []
        splitter_before = [u'before_2017']
        splitter_after = [u'after_2017-01-01']
        splitter_new = [u'after {}'.format(NEW_ALG_DATE)]
        destination = prepare_result_file_name(self)
        if not self.headers:
            raise ValueError
        if not os.path.exists(os.path.dirname(destination)):
            os.makedirs(os.path.dirname(destination))
        with open(destination, 'w') as out_file:
            writer = csv.writer(out_file)
            writer.writerow(self.headers)
            for row, ver in self.rows():
                if ver == 1:
                    if not is_added:
                        writer.writerow(splitter_before)
                        is_added = True
                    writer.writerow(row)
                elif ver == 2:
                    second_version.append(row)
                else:
                    new_version.append(row)
            if second_version:
                writer.writerow(splitter_after)
                for row in second_version:
                    writer.writerow(row)
            if new_version:
                writer.writerow(splitter_new)
                for row in new_version:
                    writer.writerow(row)

    def rows(self):
        for resp in self.response:
            r, ver = self.row(resp['value'])
            if r:
                yield r, ver


def run():
    parser = get_arguments_parser()
    parser.add_argument(
             '--kind',
             metavar='Kind',
             action=Kind,
             help='Kind filtering functionality. '
             'Usage: --kind <include, exclude, one>=<kinds>'
             )

    args = parser.parse_args()

    utility = TendersUtility(
        args.broker, args.period,
        args.config, timezone=args.timezone)
    utility.kinds = args.kind
    utility.run()


if __name__ == "__main__":
    run()
