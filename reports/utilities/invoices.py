import yaml
import requests
import requests_cache
from requests.exceptions import RequestException
from yaml.scanner import ScannerError
from reports.core import (
    ReportUtility,
    parse_args,
    thresholds_headers,
    value_currency_normalize
)

requests_cache.install_cache('audit_cache')


class InvoicesUtility(ReportUtility):

    def __init__(self):
        super(InvoicesUtility, self).__init__('invoices')
        self.view = 'report/bids_owner_date'
        self.skip_bids = set()

    def bid_date_valid(self, bid_id, audit):
        if bid_id in self.skip_bids or not audit:
            self.config.logger.info('Skipped cached early bid: %s', bid_id)
            return False
        try:
            yfile = yaml.load(requests.get(self.api_url + audit['url']).text)
            initial_bids = yfile['timeline']['auction_start']['initial_bids']
            for bid in initial_bids:
                if bid['date'] < "2016-04-01":
                    self.skip_bids.add(bid['bidder'])
        except RequestException as e:
            msg = "Request falied at getting audit file"\
                    "of {0}  bid with {1}".format(bid_id, e)
            self.logger.info(msg)
        except ScannerError:
            msg = 'falied to scan audit file of {} bid'.format(bid_id)
            self.Logger.error(msg)
        except KeyError:
            msg = 'falied to parse audit file of {} bid'.format(bid_id)
            self.logger.info(msg)

        if bid_id in self.skip_bids:
            self.logger.info('Skipped fetched early bid: %s', bid_id)
            return False
        return True

    def row(self, keys, record):
        value = record.get("value", 0)
        bid = record["bid"]
        if record.get('tender_start_date', '') < "2016-04-01" and \
                not self.bid_date_valid(bid, record.get(u'audits', '')):
            return
        if record[u'currency'] != u'UAH':
            value, rate = value_currency_normalize(
                value, record[u'currency'], keys[1]
            )
            msg = "Changing value by exgange rate {} on {}"\
                  " for value {} {} in {}".format(
                        rate, keys[1], value,
                        record[u'currency'], record['tender']
                    )
            self.Logger.info(msg)
        payment = self.get_payment(float(value))
        for i, x in enumerate(self.payments):
            if payment == x:
                msg = 'Computated bill {} for value {} '\
                      'in {} tender'.format(payment, value, record['tender'])
                self.Logger.info(msg)
                self.counter[i] += 1

    def rows(self):
        self._rows = [self.counter, self.payments]
        for resp in self.response:
            self.row(resp['key'], resp['value'])
        self._rows.append(
            [c*v for c, v in zip(self.counter, self.payments)]
        )
        for row in self._rows:
            yield row


def run():
    utility = InvoicesUtility()
    owner, period, config = parse_args()
    utility.init_from_args(owner, period, config)
    utility.headers = thresholds_headers(utility.thresholds)
    utility.counter = [0 for _ in utility.payments]
    utility.run()


if __name__ == "__main__":
    run()