// Dumps every law parameter PiaParamsAny holds, per assumption alternative,
// as JSON — the ground truth for pyanypia's params differential tests.
//
// Usage: paramdump ALT > params_altN.json   (ALT in {1,2,3})
//
// Assumption application mirrors PiaCalAny::calculate1 exactly:
// benefitIncMenu/updateCpiinc, averageWageMenu/updateFqinc, updateBases,
// updateYocAmountSpecMin.

#include <cstdlib>
#include <iostream>
#include <sstream>

#include "PiadataArray.h"
#include "UserAssumptions.h"
#include "SecondaryArray.h"
#include "piaparmsAny.h"
#include "wrkrdata.h"
#include "BaseYearNonFile.h"
#include "AwbiDataNonFile.h"
#include "AssumptionsNonFile.h"
#include "LawChangeArray.h"
#include "oactcnst.h"
#include "datemoyr.h"
#include "age.h"

using namespace std;

static string num(double d, int prec = 2)
{
  ostringstream os;
  os.setf(ios::fixed, ios::floatfield);
  os.precision(prec);
  os << d;
  return os.str();
}

#include <functional>
static string safe(const std::function<double()>& f, int prec = 2)
{
  try { return num(f(), prec); } catch (...) { return "null"; }
}

int main(int argc, char** argv)
{
  const int alt = (argc > 1) ? atoi(argv[1]) : 2;
  WorkerData::setQcLumpYear(1977);
  WorkerDataGeneral::setMaxyear(LASTYEARLR);
  BaseYearNonFile baseyear;
  const int maxyear = WorkerData::getMaxyear();
  UserAssumptions userAssumptions(LASTYEARLR);
  AwbiDataNonFile awbidat(baseyear.getYear(), maxyear);
  AssumptionsNonFile assumptions(baseyear.getYear(), maxyear);
  LawChangeArray lawChange(baseyear.getYear(), maxyear, "");
  PiaParamsAny piaparms(baseyear.getYear(), maxyear, awbidat, lawChange);
  piaparms.setHistFqinc();
  userAssumptions.setIstart(piaparms.getIstart());

  // Apply assumptions the way PiaCalAny::calculate1 does.
  const AssumptionType::assum_type aType =
    static_cast<AssumptionType::assum_type>(alt);
  assumptions.benefitIncMenu(aType);
  piaparms.updateCpiinc(assumptions.getBiProj().theData,
    assumptions.getCatchupDoc().catchup,
    assumptions.getBenefitInc(aType), assumptions.getIstart(),
    assumptions.getBiProj().theData.getLastYear());
  assumptions.averageWageMenu(aType);
  piaparms.updateFqinc(assumptions.getAwincProj().awinc,
    assumptions.getAverageWage(aType), assumptions.getIstart() - 1,
    assumptions.getAwincProj().awinc.getLastYear());
  piaparms.updateBases();
  piaparms.updateYocAmountSpecMin();

  ostream& o = cout;
  o << "{\"alt\":" << alt;
  o << ",\"istart\":" << piaparms.getIstart();
  o << ",\"maxyear\":" << maxyear;

  // Annual series.
  o << ",\"years\":{";
  bool first = true;
  for (int y = YEAR37; y <= maxyear; y++) {
    if (!first) o << ",";
    first = false;
    o << "\"" << y << "\":{";
    o << "\"fq\":" << safe([&]{ return piaparms.getFq(y); });
    o << ",\"fqinc\":" << safe([&]{ return piaparms.getFqinc(y); }, 6);
    o << ",\"cpiinc\":" << safe([&]{ return piaparms.getCpiinc(y); }, 6);
    o << ",\"base_oasdi\":" << safe([&]{ return piaparms.getBaseOasdi(y); });
    o << ",\"base_77\":" << safe([&]{ return piaparms.getBase77(y); });
    o << ",\"base_hi\":" << safe([&]{ return piaparms.getBaseHi(y); });
    o << ",\"qc_amt\":" << safe([&]{ return piaparms.qcamt[y]; });
    o << ",\"yoc_amt_specmin\":" << safe([&]{ return piaparms.getYocAmountSpecMin(y); });
    if (y >= 1979) {
      o << ",\"bp_pia\":[" << safe([&]{ return piaparms.bpPiaOut.getBppia(y, 1); }) << ","
        << safe([&]{ return piaparms.bpPiaOut.getBppia(y, 2); }) << "]";
      o << ",\"bp_mfb\":[" << safe([&]{ return piaparms.bpMfbOut.getBpmfb1(y); }) << ","
        << safe([&]{ return piaparms.bpMfbOut.getBpmfb2(y); }) << ","
        << safe([&]{ return piaparms.bpMfbOut.getBpmfb3(y); }) << "]";
    }
    o << "}";
  }
  o << "}";

  // Retirement ages / credits by year of attaining age 62 (eligYear).
  o << ",\"elig_years\":{";
  first = true;
  for (int y = 1940; y <= maxyear; y++) {
    if (!first) o << ",";
    first = false;
    o << "\"" << y << "\":{";
    try {
      const Age nra = piaparms.fullRetAgeCal(y);
      o << "\"nra\":[" << nra.getYears() << "," << nra.getMonths() << "]";
    } catch (...) { o << "\"nra\":null"; }
    try {
      const Age dibmax = piaparms.maxDibAge(y);
      o << ",\"max_dib_age\":[" << dibmax.getYears() << ","
        << dibmax.getMonths() << "]";
    } catch (...) { o << ",\"max_dib_age\":null"; }
    o << ",\"ret_credit\":" << safe([&]{ return PiaParams::retCredit(y); }, 6);
    o << "}";
  }
  o << "}";

  // Actuarial reduction factor per month of early retirement (OAB).
  o << ",\"factor_ar\":[";
  for (int m = 0; m <= 72; m++) {
    if (m > 0) o << ",";
    o << safe([&]{ return piaparms.factorArCal(m); }, 8);
  }
  o << "]";

  // Special minimum PIA table: December of each year, by years of coverage.
  o << ",\"spec_min_pia\":{";
  first = true;
  for (int y = 1979; y <= maxyear; y++) {
    if (!first) o << ",";
    first = false;
    o << "\"" << y << "\":[";
    for (int yoc = 1; yoc <= 20; yoc++) {
      if (yoc > 1) o << ",";
      o << safe([&]{ return piaparms.getSpecMinPia(DateMoyr(12, y), yoc); });
    }
    o << "]";
  }
  o << "}";

  o << "}" << endl;
  return 0;
}
