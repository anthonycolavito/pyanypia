// JSON-instrumented variant of SSA's anypiab batch driver.
//
// Reads one big .pia file with many cases (name given on stdin, like the
// ONEBIGFILE build of anypiab) and writes one JSON object per case to
// "output.jsonl": final results plus per-method intermediates, so a
// divergence in the Python port localizes to a single computation.
//
// The calculation call sequence is IDENTICAL to AnypiabDoc::calculate();
// only the output side differs.

#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "PiadataArray.h"
#include "UserAssumptions.h"
#include "SecondaryArray.h"
#include "EarnProject.h"
#include "piaparmsAny.h"
#include "wrkrdata.h"
#include "WorkerDataArray.h"
#include "BaseYearNonFile.h"
#include "AwbiDataNonFile.h"
#include "AssumptionsNonFile.h"
#include "LawChangeArray.h"
#include "piareadAny.h"
#include "PiaCalAny.h"
#include "pebs.h"
#include "LawChangeRead.h"
#include "PiaException.h"
#include "PiaMethod.h"
#include "Secondary.h"
#include "DateFormatter.h"
#include "Path.h"
#include "Trace.h"
#include "TextWriterTraceListener.h"

using namespace std;

static const char* methodName(PiaMethod::pia_type t)
{
  switch (t) {
    case PiaMethod::OLD_START: return "OLD_START";
    case PiaMethod::PIA_TABLE: return "PIA_TABLE";
    case PiaMethod::WAGE_IND: return "WAGE_IND";
    case PiaMethod::TRANS_GUAR: return "TRANS_GUAR";
    case PiaMethod::SPEC_MIN: return "SPEC_MIN";
    case PiaMethod::REIND_WID: return "REIND_WID";
    case PiaMethod::FROZ_MIN: return "FROZ_MIN";
    case PiaMethod::CHILD_CARE: return "CHILD_CARE";
    case PiaMethod::DIB_GUAR: return "DIB_GUAR";
    case PiaMethod::WAGE_IND_NON_FREEZE: return "WAGE_IND_NON_FREEZE";
    default: return "NO_PIA_TYPE";
  }
}

// Formats a double with enough precision for exact-cent comparison.
static string num(double d)
{
  ostringstream os;
  os.setf(ios::fixed, ios::floatfield);
  os.precision(2);
  os << d;
  return os.str();
}

class JsonDoc
{
public:
  BaseYearNonFile* baseyear;
  AwbiDataNonFile* awbidat;
  PiaParamsAny* piaparms;
  Assumptions* assumptions;
  LawChangeArray* lawChange;
  UserAssumptions* userAssumptions;
  SecondaryArray* secondaryArray;
  EarnProject* earnProject;
  PiaReadAny* piaread;
  PiaCalAny* piacal;
  Pebs* pebs;
  WorkerData* workerData;
  PiaData* piaData;
  WorkerDataArray* widowDataArray;
  PiaDataArray* widowPiaDataArray;

  JsonDoc()
  {
    WorkerData::setQcLumpYear(1977);
    WorkerDataGeneral::setMaxyear(LASTYEARLR);
    baseyear = new BaseYearNonFile();
    workerData = new WorkerData;
    piaData = new PiaData;
    widowDataArray = new WorkerDataArray;
    widowPiaDataArray = new PiaDataArray;
    userAssumptions = new UserAssumptions(LASTYEARLR);
    secondaryArray = new SecondaryArray();
    earnProject = new EarnProject(LASTYEARLR);
    pebs = new Pebs;
    piaread = new PiaReadAny(*workerData, *widowDataArray,
      *widowPiaDataArray, *userAssumptions, *secondaryArray, *earnProject,
      *pebs);
    awbidat = new AwbiDataNonFile(baseyear->getYear(),
      WorkerData::getMaxyear());
    assumptions = new AssumptionsNonFile(baseyear->getYear(),
      WorkerData::getMaxyear());
    lawChange = new LawChangeArray(baseyear->getYear(),
      WorkerData::getMaxyear(), "");
    // A reform run supplies lawchg.dat next to the case file; without one
    // every indicator stays 0 and the law-change machinery is inert.
    {
      ifstream lawchgTest("lawchg.dat");
      if (lawchgTest.is_open()) {
        lawchgTest.close();
        LawChangeRead(*lawChange).read();
        cerr << "lawchg.dat applied ("
             << lawChange->getIndTotal() << " changes)" << endl;
      }
    }
    piaparms = new PiaParamsAny(baseyear->getYear(),
      WorkerData::getMaxyear(), *awbidat, *lawChange);
    piaparms->setHistFqinc();
    piacal = new PiaCalAny(*workerData, *piaData, *widowDataArray,
      *widowPiaDataArray, *piaparms, *userAssumptions, *secondaryArray,
      *lawChange, *pebs, *earnProject);
  }

  void savecaseJson(ostream& out)
  {
    ostringstream j;
    j.setf(ios::fixed, ios::floatfield);
    j << "{\"id\":\"" << workerData->ssn.toString() << "\"";
    j << ",\"joasdi\":" << static_cast<int>(workerData->getJoasdi());
    j << ",\"dob\":\""
      << DateFormatter::toString(workerData->getBirthDate(), "s") << "\"";
    j << ",\"fins\":\"" << piaData->getFinsCode2() << "\"";
    // disInsCode is only computed for a disability case and is not
    // cleared between cases, so anything else would report the previous
    // disability case in the batch.
    j << ",\"dib_insured\":"
      << ((workerData->getJoasdi() == WorkerData::DISABILITY &&
           piaData->disInsCode.isDisabilityInsured()) ? "true" : "false");
    j << ",\"elig_year\":" << piaData->getEligYear();
    j << ",\"high_pia\":" << num(piaData->highPia.get());
    j << ",\"high_mfb\":" << num(piaData->highMfb.get());
    j << ",\"support_pia\":" << num(piaData->supportPia.get());
    // The worker has no benefit of their own in a survivor case, and
    // PiaData::initialize() does not clear these four, so without this
    // guard they would report whatever the previous case in the batch
    // left behind.
    const bool workerBen =
      workerData->getJoasdi() != WorkerData::SURVIVOR;
    j << ",\"unrounded_benefit\":"
      << num(workerBen ? piaData->unroundedBenefit.get() : 0.0);
    j << ",\"rounded_benefit\":"
      << num(workerBen ? piaData->roundedBenefit.get() : 0.0);
    j << ",\"months_ardri\":"
      << (workerBen ? piaData->getMonthsArdri() : 0);
    j << ",\"age_ben_years\":"
      << (workerBen ? piaData->ageBen.getYears() : 0);
    j << ",\"age_ben_months\":"
      << (workerBen ? piaData->ageBen.getMonths() : 0);
    j << ",\"pifc\":\"" << piaData->getPifc() << "\"";
    // A Statement case runs the whole calculation five times over
    // mutated inputs, so its answers live in Pebs rather than PiaData.
    if (workerData->getJoasdi() == WorkerData::PEBS_CALC) {
      j << ",\"pebs\":{";
      j << "\"oab_early\":" << pebs->getBenefitPebs(Pebs::PEBS_OAB_EARLY);
      j << ",\"oab_full\":" << pebs->getBenefitPebs(Pebs::PEBS_OAB_FULL);
      j << ",\"oab_delayed\":"
        << pebs->getBenefitPebs(Pebs::PEBS_OAB_DELAYED);
      j << ",\"surv_benefit\":" << pebs->getBenefitPebs(Pebs::PEBS_SURV);
      j << ",\"surv_pia\":" << pebs->getPiaPebs(Pebs::PEBS_SURV);
      j << ",\"surv_mfb\":" << pebs->getMfbPebs(Pebs::PEBS_SURV);
      j << ",\"disab_pia\":" << pebs->getPiaPebs(Pebs::PEBS_DISAB);
      j << ",\"disab_mfb\":" << pebs->getMfbPebs(Pebs::PEBS_DISAB);
      j << ",\"qc_total\":" << pebs->getQcTotal();
      j << ",\"qc_dis_req\":" << pebs->getQcDisReq();
      j << ",\"qc_dis_total\":" << pebs->getQcDisTotal();
      j << ",\"pebs_oab\":" << pebs->getPebsOab();
      j << ",\"pebs_dib\":" << pebs->getPebsDib();
      j << ",\"age_now_years\":" << pebs->ageNow.getYears();
      j << ",\"age_now_months\":" << pebs->ageNow.getMonths();
      j << "}";
    }
    if (piacal->highPiaMethod != 0) {
      j << ",\"high_method\":\""
        << methodName(piacal->highPiaMethod->getMethod()) << "\"";
    }
    // per-method intermediates
    j << ",\"methods\":[";
    for (size_t i = 0; i < piacal->piaMethod.size(); i++) {
      const PiaMethod* m = piacal->piaMethod[i];
      if (i > 0) j << ",";
      j << "{\"method\":\"" << methodName(m->getMethod()) << "\"";
      j << ",\"applicable\":" << static_cast<int>(m->getApplicable());
      j << ",\"ame\":" << num(m->getAme());
      j << ",\"pia\":" << num(m->piaEnt.get());
      j << ",\"mfb\":" << num(m->mfbEnt.get());
      j << "}";
    }
    j << "]";
    // family members
    j << ",\"secondaries\":[";
    for (int i = 0; i < piacal->widowArray.getFamSize(); i++) {
      const Secondary* s = piacal->secondaryArray.secondary[i];
      if (i > 0) j << ",";
      j << "{\"bic\":\"" << s->bic.toString() << "\"";
      j << ",\"full_benefit\":" << num(s->getFullBenefit());
      j << ",\"rounded_benefit\":" << num(s->getRoundedBenefit());
      j << ",\"pifc\":\"" << s->pifc.get() << "\"";
      j << "}";
    }
    j << "]}";
    out << j.str() << "\n";
  }

  int calculate()
  {
    ifstream in;
    char ernfil[80];
    int ierr = 0;
    int rval = 0;
    ofstream out("output.jsonl");
    string infile;

    userAssumptions->setIstart(piaparms->getIstart());
    cin >> ernfil;
    infile = Path::changeExtension(ernfil, "pia");
    in.open(infile.c_str());
    if (in.fail()) {
      cerr << "Unable to open input file " << infile << endl;
      return 1;
    }
    while (!in.fail() && ierr == 0) {
      try {
        workerData->deleteContents();
        piaData->deleteContents();
        earnProject->deleteContents();
        widowDataArray->deleteContents();
        widowPiaDataArray->deleteContents();
        secondaryArray->deleteContents();
        ierr = piaread->read(in);
        if (ierr == 0 || ierr == PIA_IDS_READEOF ||
            ierr == PIA_IDS_READMORE) {
          DateMoyr entDate =
            (workerData->getJoasdi() == WorkerDataGeneral::SURVIVOR) ?
            secondaryArray->secondary[0]->entDate :
            workerData->getEntDate();
          piacal->dataCheck(entDate);
          piacal->dataCheckAux(*widowDataArray, *widowPiaDataArray,
            *secondaryArray);
          piacal->calculate1(*assumptions);
          piacal->calculate2(entDate);
          piacal->reindWidCalAll(*widowDataArray, *widowPiaDataArray,
            *secondaryArray);
          piacal->piaCal3(*widowPiaDataArray, *secondaryArray);
          savecaseJson(out);
        } else {
          PiaException e(ierr);
          out << "{\"id\":\"" << workerData->getIdString()
              << "\",\"error\":\"" << e.what() << " in file read\"}" << "\n";
          rval = 2;
        }
      } catch (PiaException& e) {
        out << "{\"id\":\"" << workerData->getIdString()
            << "\",\"error\":\"" << e.what() << " in calculation\"}" << "\n";
        rval = 2;
      }
    }
    in.close();
    out.close();
    return rval;
  }
};

int main(int, char**)
{
  TextWriterTraceListener outputLog(&cerr);
  Trace::getListeners().push_back(&outputLog);
  JsonDoc doc;
  return doc.calculate();
}
