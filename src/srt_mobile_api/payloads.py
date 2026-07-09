from .models import TrainSearchQuery


def search_page_payload(
    query: TrainSearchQuery,
    depart_name: str,
    arrive_name: str,
    netfunnel_key: str,
) -> dict[str, str]:
    payload = {
        "jobId": "1101",
        "jrnyTpCd": "11",
        "jrnyCnt": "1",
        "grpDv": "0",
        "rtnDv": "0",
        "stlbTrnClsfCd1": "05",
        "stndFlg": "N",
        "jrnySqno1": "001",
        "trnGpCd1": query.train_group_code,
        "trnGpNm1": "전체",
        "dptRsStnCd1": query.departure_station_code,
        "dptRsStnCdNm1": depart_name,
        "arvRsStnCd1": query.arrival_station_code,
        "arvRsStnCdNm1": arrive_name,
        "dptDt1": query.departure_date,
        "dptTm1": query.departure_time,
        "totPrnb": str(query.passengers.total),
        "totPrnbNm": f"{query.passengers.total}명",
        "psgGridcnt": str(query.passengers.total),
        "psgTpCd1": "1",
        "psgInfoPerPrnb1": str(query.passengers.adult),
        "seatAttCd": query.seat_attr_code,
        "netfunnelKey": netfunnel_key,
        "adjStnScdlOfrFlg": "N",
    }
    for key in ["jrnySqno2", "trnGpCd2", "trnGpNm2", "arvDt1", "arvTm1", "pnrNo", "JRNYLIST_KEY"]:
        payload.setdefault(key, "")
    for leg in (1, 2):
        for idx in range(1, 10):
            payload[f"seatNo{leg}_{idx}"] = ""
    return payload


def search_ajax_payload(query: TrainSearchQuery, netfunnel_key: str) -> dict[str, str]:
    return {
        "chtnDvCd": "1",
        "dptDt": query.departure_date,
        "dptTm": query.departure_time,
        "dptDt1": query.departure_date,
        "dptTm1": query.departure_time,
        "dptRsStnCd": query.departure_station_code,
        "arvRsStnCd": query.arrival_station_code,
        "stlbTrnClsfCd": "05",
        "trnGpCd": query.train_group_code,
        "trnNo": "",
        "psgNum": str(query.passengers.total),
        "seatAttCd": query.seat_attr_code,
        "arriveTime": "N",
        "tkDptDt": "",
        "tkDptTm": "",
        "tkTrnNo": "",
        "tkTripChgFlg": "",
        "dlayTnumAplFlg": "Y",
        "netfunnelKey": netfunnel_key,
        "disability": "N",
        "adjStnScdlOfrFlg": "N",
    }


def group_search_ajax_payload(query: TrainSearchQuery, netfunnel_key: str) -> dict[str, str]:
    payload = search_ajax_payload(query, netfunnel_key)
    payload["grpDv"] = "1"
    payload["psgNum"] = str(max(query.passengers.total, 10))
    return payload
