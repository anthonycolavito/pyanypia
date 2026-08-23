# Builds SSA's anypiab (batch Detailed Calculator) from the vendored source.
#
# Vendor sources are copied to oracle/work/ and patches from oracle/patches/
# are applied there; oracle/vendor/ itself is never modified.
#
# Targets: all (default), anypiab, prepare, clean
# Flags: -DANYPIAB selects the AnypiabDoc driver; -DONEBIGFILE makes it read
# one file containing many cases (filename given on stdin, .pia appended).

ORACLE := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))..)
VENDOR := $(ORACLE)/vendor
WORK   := $(ORACLE)/work
BIN    := $(ORACLE)/bin
OBJ    := $(WORK)/obj

# Boost headers: from Homebrew when present, otherwise already on the
# default include path. Never pass -isystem /usr/include -- on GCC that
# reorders the standard include search and breaks #include_next.
BOOST_PREFIX := $(shell brew --prefix boost 2>/dev/null)
ifneq ($(wildcard $(BOOST_PREFIX)/include/boost/version.hpp),)
  BOOST_FLAGS := -isystem $(BOOST_PREFIX)/include
else
  BOOST_FLAGS :=
endif

CXX      ?= c++
CXXFLAGS := -O2 -std=c++14 -w -DANYPIAB -DONEBIGFILE \
  -I$(WORK)/oactobjs32/linux -I$(WORK)/oactobjs32/include \
  $(BOOST_FLAGS)

.PHONY: all anypiab prepare clean compile

all: anypiab anypiab-json paramdump

# Stage sources into work tree and apply patches, then build in a sub-make so
# wildcards see the staged files.
prepare:
	@mkdir -p $(WORK) $(BIN) $(OBJ)
	@rsync -a --delete --exclude obj --exclude cases $(VENDOR)/ $(WORK)/src-stamp-ignore 2>/dev/null || true
	@rm -rf $(WORK)/oactobjs32 $(WORK)/source32
	@cp -R $(VENDOR)/oactobjs32 $(VENDOR)/source32 $(WORK)/
	@find $(WORK)/oactobjs32 $(WORK)/source32 \( -name '*.cpp' -o -name '*.h' -o -name '*.H' \) \
	  -exec perl -pi -e 's/\r$$//' {} +
	@if ls $(ORACLE)/patches/*.patch >/dev/null 2>&1; then \
	  for p in $(ORACLE)/patches/*.patch; do \
	    echo "applying $$p"; patch -d $(WORK) -p1 < $$p || exit 1; \
	  done; fi

anypiab: prepare
	@$(MAKE) --no-print-directory compile

anypiab-json: prepare
	@$(MAKE) --no-print-directory compile-json

paramdump: prepare
	@$(MAKE) --no-print-directory compile-paramdump

# ---- second stage (work tree exists) ----

# BitAnnual is split: misc/BitAnnual.cpp + linux/BitAnnual.cpp are complementary
# halves of the class (see patches/0001), so both are compiled.
SRC_MISC    := $(wildcard $(WORK)/oactobjs32/misc/*.cpp)
SRC_LINUX   := $(wildcard $(WORK)/oactobjs32/linux/*.cpp)
SRC_PIADATA := $(wildcard $(WORK)/oactobjs32/piadata/*.cpp)
SRC_DRIVER  := $(WORK)/source32/anypiab/anypiab.cpp \
               $(WORK)/source32/anypiab/anypiabdoc.cpp

LIB_SRCS := $(SRC_MISC) $(SRC_LINUX) $(SRC_PIADATA)
LIB_OBJS := $(patsubst $(WORK)/%.cpp,$(OBJ)/%.o,$(LIB_SRCS))
DRV_OBJS := $(patsubst $(WORK)/%.cpp,$(OBJ)/%.o,$(SRC_DRIVER))

$(OBJ)/%.o: $(WORK)/%.cpp
	@mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) -c $< -o $@

$(WORK)/liboact.a: $(LIB_OBJS)
	ar rcs $@ $^

compile: $(BIN)/anypiab

compile-json: $(BIN)/anypiab-json

$(OBJ)/anypiabjson.o: $(ORACLE)/instrumented/anypiabjson.cpp
	@mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) -c $< -o $@

$(BIN)/anypiab-json: $(OBJ)/anypiabjson.o $(WORK)/liboact.a
	$(CXX) $(CXXFLAGS) -o $@ $(OBJ)/anypiabjson.o $(WORK)/liboact.a

compile-paramdump: $(BIN)/paramdump

$(OBJ)/paramdump.o: $(ORACLE)/instrumented/paramdump.cpp
	@mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) -c $< -o $@

$(BIN)/paramdump: $(OBJ)/paramdump.o $(WORK)/liboact.a
	$(CXX) $(CXXFLAGS) -o $@ $(OBJ)/paramdump.o $(WORK)/liboact.a

$(BIN)/anypiab: $(DRV_OBJS) $(WORK)/liboact.a
	$(CXX) $(CXXFLAGS) -o $@ $(DRV_OBJS) $(WORK)/liboact.a

clean:
	rm -rf $(WORK) $(BIN)
