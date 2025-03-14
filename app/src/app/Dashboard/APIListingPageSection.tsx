import * as React from 'react';
import { Button, Card, CardBody, Flex, FlexItem, Label, PageSection, Pagination, Title, Toolbar, ToolbarContent, ToolbarItem } from '@patternfly/react-core';
import { APIListingTable} from '@app/Dashboard/APIListingTable';
import { APIModal } from './Modal/APIModal';
import { APICheckSpecModal } from './Modal/APICheckSpecModal';
import { APIExportSPDXModal } from './Modal/APIExportSPDXModal';

export interface APIListingPageSectionProps {
  baseApiUrl: string;
  currentLibrary: string;
  setCurrentLibrary;
  loadLibraries;
  loadApi;
  apis;
  totalCoverage;
  searchValue: string;
}

const APIListingPageSection: React.FunctionComponent<APIListingPageSectionProps> = ({
  baseApiUrl,
  currentLibrary,
  setCurrentLibrary,
  loadLibraries,
  loadApi,
  apis,
  totalCoverage,
  searchValue,
  }: APIListingPageSectionProps) => {
  const rows = [];
  const [page, setPage] = React.useState(1);
  const [modalShowState, setModalShowState] = React.useState(false);
  const [modalCheckSpecShowState, setModalCheckSpecShowState] = React.useState(false);
  const [modalSPDXExportShowState, setModalSPDXExportShowState] = React.useState(false);
  const [modalCheckSpecApiData, setModalCheckSpecApiData] = React.useState(null);
  const [modalObject, setModalObject] = React.useState('');
  const [modalAction, setModalAction] = React.useState('');
  const [modalVerb, setModalVerb] = React.useState('');
  const [modalFormData, setModalFormData] = React.useState('');
  const [modalTitle, setModalTitle] = React.useState('');
  const [modalDescription, setModalDescription] = React.useState('');
  const [perPage, setPerPage] = React.useState(10);
  const [SPDXContent, setSPDXContent] = React.useState('');

  /* eslint-disable @typescript-eslint/no-unused-vars */
  const [paginatedRows, setPaginatedRows] = React.useState(rows.slice(0, 10));
  const handleSetPage = (_evt, newPage, perPage, startIdx, endIdx) => {
    setPaginatedRows(rows.slice(startIdx, endIdx));
    setPage(newPage);
  };
  const handlePerPageSelect = (_evt, newPerPage, newPage, startIdx, endIdx) => {
    setPaginatedRows(rows.slice(startIdx, endIdx));
    setPage(newPage);
    setPerPage(newPerPage);
  };

  const setModalInfo = (_modalData, _modalShowState, _modalObject, _modalVerb, _modalAction, _modalTitle, _modalDescription) => {
    setModalFormData(_modalData);
    setModalShowState(_modalShowState);
    setModalObject(_modalObject);
    setModalVerb(_modalVerb);
    setModalAction(_modalAction);
    setModalTitle(_modalTitle);
    setModalDescription(_modalDescription);
  }

  const setModalCheckSpecInfo = (_api, _modalShowState) => {
    setModalCheckSpecShowState(_modalShowState);
    setModalCheckSpecApiData(_api);
  }

  const exportSPDX = () => {
    fetch(baseApiUrl + '/spdx/libraries?library=' + currentLibrary)
      .then((res) => res.json())
      .then((data) => {
        setSPDXContent(JSON.stringify(data, null, 2));
        setModalSPDXExportShowState(true);
      })
      .catch((err) => {
        console.log(err.message);
      });
  }

  const renderPagination = (variant, isCompact) => (
    <Pagination
      isCompact={isCompact}
      itemCount={rows.length}
      page={page}
      perPage={perPage}
      onSetPage={handleSetPage}
      onPerPageSelect={handlePerPageSelect}
      variant={variant}
      titles={{
        paginationAriaLabel: `${variant} pagination`
      }}
    />
  );

  const tableToolbar = (
    <Toolbar usePageInsets id="compact-toolbar">
      <ToolbarContent>
        <ToolbarItem variant="pagination">{renderPagination('top', true)}</ToolbarItem>
      </ToolbarContent>
    </Toolbar>
  );

  let emptyFormData = {'id': 0,
                       'api': '',
                       'library': '',
                       'library_version': '',
                       'raw_specification_url': '',
                       'category': '',
                       'tags': '',
                       'implementation_file_from_row': '',
                       'implementation_file_to_row': '',
                       'implementation_file': '',},

  return (
    <PageSection isFilled>
      <Card>
        <CardBody>
          <Flex>
            <Flex>
              <FlexItem>
                <Title headingLevel="h1">API Listing for {currentLibrary}</Title>
              </FlexItem>
              <FlexItem>
                <Label color="green" isCompact>Covered {totalCoverage}%</Label>
              </FlexItem>
            </Flex>
            <Flex align={{ default: 'alignRight' }}>
              <FlexItem>
                <Button variant="primary"
                  onClick={() => setModalInfo(emptyFormData,
                                              true,
                                              'api',
                                              'POST',
                                              'add',
                                              'Software Component',
                                              'Add a new software component')}
                  >Add Software Component
                </Button>
              </FlexItem>
              <FlexItem>
                <Button
                  variant="secondary"
                  onClick={() => exportSPDX()}
                >Export to SPDX
                </Button>
              </FlexItem>
              <FlexItem><Button variant="secondary" isDisabled>Baseline</Button></FlexItem>
            </Flex>
          </Flex>
          {tableToolbar}
          <APIListingTable
            currentLibrary={currentLibrary}
            searchValue={searchValue}
            baseApiUrl={baseApiUrl}
            setModalInfo={setModalInfo}
            setModalCheckSpecInfo={setModalCheckSpecInfo}
            apis={apis}/>
        </CardBody>
      </Card>
      <APIModal
        modalAction={modalAction}
        modalVerb={modalVerb}
        modalObject={modalObject}
        modalTitle={modalTitle}
        modalDescription={modalDescription}
        modalFormData={modalFormData}
        modalShowState={modalShowState}
        setModalShowState={setModalShowState}
        setCurrentLibrary={setCurrentLibrary}
        loadLibraries={loadLibraries}
        loadApi={loadApi}
        baseApiUrl={baseApiUrl} />
      <APICheckSpecModal
        baseApiUrl={baseApiUrl}
        modalShowState={modalCheckSpecShowState}
        setModalShowState={setModalCheckSpecShowState}
        api={modalCheckSpecApiData} />
      <APIExportSPDXModal
        SPDXContent={SPDXContent}
        setSPDXContent={setSPDXContent}
        modalShowState={modalSPDXExportShowState}
        setModalShowState={setModalSPDXExportShowState}/>
    </PageSection>
  )
}

export { APIListingPageSection };
