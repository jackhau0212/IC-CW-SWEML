"""
Unit tests to confirm the message processing steps 
are working as intended. 

"""

from model import from_mllp, to_mllp, pas_process, lims_process
import numpy as np

def test_from_mllp() -> bool:
    """
    Tests MLLP messages are processed correctly.
    """
    msg1 = b'\x0bMSH|^~\\&|SIMULATION|SOUTH RIVERSIDE|||20240102135300||ADT^A01|||2.5\rPID|1||497030||ROSCOE DOHERTY||19870515|M\r\x1c\r'
    e1 = ['MSH|^~\\&|SIMULATION|SOUTH RIVERSIDE|||20240102135300||ADT^A01|||2.5',
                'PID|1||497030||ROSCOE DOHERTY||19870515|M']
    a1 = from_mllp(msg1)

    assert e1 == a1

    msg2 = b'\x0bMSH|^~\&|SIMULATION|SOUTH RIVERSIDE|||20240310134000||ADT^A01|||2.5\rPID|1||160116||AJAY BURTON||20010829|M\r\x1c\r'
    e2 = ['MSH|^~\&|SIMULATION|SOUTH RIVERSIDE|||20240310134000||ADT^A01|||2.5', 
          'PID|1||160116||AJAY BURTON||20010829|M']
    a2 = from_mllp(msg2)

    assert e2 == a2

    msg3 = b'\x0bMSH|^~\&|SIMULATION|SOUTH RIVERSIDE|||20240401084800||ORU^R01|||2.5\rPID|1||265445\rOBR|1||||||20240401084800\rOBX|1|SN|CREATININE||116.05310027497755\r\x1c\r'
    e3 = ['MSH|^~\&|SIMULATION|SOUTH RIVERSIDE|||20240401084800||ORU^R01|||2.5',
          'PID|1||265445',
          'OBR|1||||||20240401084800',
          'OBX|1|SN|CREATININE||116.05310027497755']
    a3 = from_mllp(msg3)

    assert e3 == a3
    
def test_to_mllp() -> bool:
    """
    Tests messages are converted to MLLP format correctly
    """

    msg1 = ['MSH|^~\\&|SIMULATION|SOUTH RIVERSIDE|||20240102135300||ADT^A01|||2.5',
                'PID|1||497030||ROSCOE DOHERTY||19870515|M']
    e1 =  b'\x0bMSH|^~\\&|SIMULATION|SOUTH RIVERSIDE|||20240102135300||ADT^A01|||2.5\rPID|1||497030||ROSCOE DOHERTY||19870515|M\r\x1c\r'
    a1 = to_mllp(msg1)

    assert e1 == a1

    msg2 = ['MSH|^~\&|SIMULATION|SOUTH RIVERSIDE|||20240310134000||ADT^A01|||2.5', 
          'PID|1||160116||AJAY BURTON||20010829|M']
    e2 = b'\x0bMSH|^~\&|SIMULATION|SOUTH RIVERSIDE|||20240310134000||ADT^A01|||2.5\rPID|1||160116||AJAY BURTON||20010829|M\r\x1c\r'
    a2 = to_mllp(msg2)

    assert a2 == e2

    msg3 = ['MSH|^~\&|SIMULATION|SOUTH RIVERSIDE|||20240401084800||ORU^R01|||2.5',
          'PID|1||265445',
          'OBR|1||||||20240401084800',
          'OBX|1|SN|CREATININE||116.05310027497755']
    e3 = b'\x0bMSH|^~\&|SIMULATION|SOUTH RIVERSIDE|||20240401084800||ORU^R01|||2.5\rPID|1||265445\rOBR|1||||||20240401084800\rOBX|1|SN|CREATININE||116.05310027497755\r\x1c\r'
    a3 = to_mllp(msg3)

    assert a3 == e3

def test_pas_process() -> bool:
    """
    Tests recieved PAS messages are processed correctly.
    """
    db = {}

    msg = ['MSH|^~\\&|SIMULATION|SOUTH RIVERSIDE|||20240102135300||ADT^A03|||2.5',
            'PID|1||497030||ROSCOE DOHERTY||19870515|M']
    pas_process(497030, msg, db)

    assert db == {}

    msg = ['MSH|^~\\&|SIMULATION|SOUTH RIVERSIDE|||20240102135300||ADT^A01|||2.5',
            'PID|1||497030||ROSCOE DOHERTY||19870515|M']
    
    pas_process(497030, msg, db)
    

    assert db == {497030: {"results": [],
                 "sex": 'M',
                 "age": 36}}
    
    msg = ['MSH|^~\\&|SIMULATION|SOUTH RIVERSIDE|||20240102135300||ADT^A01|||2.5',
            'PID|1||497030||ROSCOE DOHERTY||19870515|F']
    
    pas_process(497030, msg, db)

    assert db == {497030: {"results": [],
                 "sex": 'F',
                 "age": 36}}
    
    msg = ['MSH|^~\&|SIMULATION|SOUTH RIVERSIDE|||20240310134000||ADT^A01|||2.5', 
          'PID|1||160116||AJAY BURTON||20010829|M']

    pas_process(160116, msg, db)

    assert db == {  497030:  {"results": [],
                            "sex": 'F',
                            "age": 36}, 
                    160116 : {"results": [],
                            "sex": 'M',
                            "age": 22}
                    }
def test_lims_process():
    """
    Tests LIMS messages are correctly added to the DB
    """
    db =    {497030:  {  "results": [],
                        "sex": 'F',
                        "age": 36
                        }, 
            160116 : {  "results": [],
                        "sex": 'M',
                        "age": 22
                        }}
    
    result = ["MSH|^~\&|SIMULATION|SOUTH RIVERSIDE|||20240404171700||ORU^R01|||2.5",
              "PID|1||497030",
              "OBR|1||||||20240404171700",
              "OBX|1|SN|CREATININE||70.69681868961705"]
    
    tp = lims_process(497030, result, db)

    assert db == {497030:  {"results": [70.69681868961705],
                            "sex": 'F',
                            "age": 36}, 
                  160116 : {"results": [],
                            "sex": 'M',
                            "age": 22}}
    
    np.testing.assert_array_equal(tp, np.array([36., 0., 70.69681868961705, 70.69681868961705, 70.69681868961705, 70.69681868961705, 70.69681868961705]).reshape(1,-1))
    

def run_tests():
    test_to_mllp()
    test_from_mllp()
    test_pas_process()
    test_lims_process()
    print("All tests passed!")


if __name__ == "__main__":
   run_tests()