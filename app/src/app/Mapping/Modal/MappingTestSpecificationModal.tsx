import React from 'react';
import { Modal, ModalVariant, Form, FormGroup, Popover, Button, TextInput} from '@patternfly/react-core';
import { Tabs, Tab, TabTitleText, TabContent, TabContentBody } from '@patternfly/react-core';
import { SectionForm } from '../Form/SectionForm';
import { TestSpecificationForm } from '../Form/TestSpecificationForm';
import { TestSpecificationSearch } from '../Search/TestSpecificationSearch';

export interface MappingTestSpecificationModalProps {
  api;
  baseApiUrl: string;
  modalAction: string;
  modalVerb: string;
  modalObject: string;
  modalTitle: string;
  modalDescription: string;
  modalShowState: string;
  modalFormData;
  modalIndirect;
  modalOffset;
  modalSection;
  setModalShowState;
  loadMappingData;
  parentData;
  parentType;
  parentRelatedToType;
  setModalOffset,
  setModalSection,
}

export const MappingTestSpecificationModal: React.FunctionComponent<MappingTestSpecificationModalProps> = ({
  baseApiUrl,
  modalShowState = false,
  setModalShowState,
  setCurrentLibrary,
  modalObject = "",
  modalAction = "",
  modalVerb = "",
  modalTitle = "",
  modalFormData,
  modalIndirect,
  modalOffset,
  modalSection,
  modalDescription = "",
  api,
  loadMappingData,
  parentData,
  parentType,
  parentRelatedToType,
  setModalOffset,
  setModalSection,
  }: MappingTestSpecificationModalProps) => {
  const [isModalOpen, setIsModalOpen] = React.useState(false);
  let [modalFormSubmitState, setModalFormSubmitState] = React.useState('waiting');

  const handleModalConfirm = () => {
    setModalFormSubmitState('submitted');
  }


  const handleModalToggle = (_event: KeyboardEvent | React.MouseEvent) => {
    let new_state = !modalShowState;
    setModalShowState(new_state);
    setIsModalOpen(new_state);
  };

  React.useEffect(() => {
    setIsModalOpen(modalShowState);
  }, [modalShowState]);


  const [activeTabKey, setActiveTabKey] = React.useState<string | number>(0);
  // Toggle currently active tab
  const handleTabClick = (
  event: React.MouseEvent<any> | React.KeyboardEvent | MouseEvent,
  tabIndex: string | number
  ) => {
  setActiveTabKey(tabIndex);
  };

  const newItemRef = React.createRef<HTMLElement>();
  const sectionItemsRef = React.createRef<HTMLElement>();
  const existingItemsRef = React.createRef<HTMLElement>();

  return (
    <React.Fragment>
      <Modal
        bodyAriaLabel="Scrollable modal content"
        tabIndex={0}
        variant={ModalVariant.large}
        title={modalTitle}
        description={modalDescription}
        isOpen={isModalOpen}
        onClose={handleModalToggle}
        actions={[
          <Button key="cancel" variant="link" onClick={handleModalToggle}>
            Cancel
          </Button>
        ]}
      >

      <Tabs
        activeKey={activeTabKey}
        onSelect={handleTabClick}
        aria-label="Add a New/Existing Test Specification"
        role="region"
      >
        <Tab
          eventKey={0}
          title={<TabTitleText>Test Specification Data</TabTitleText>}
          tabContentId="tabNewTestSpecification"
          tabContentRef={newItemRef}
        />
        <Tab
          eventKey={1}
          isDisabled={modalIndirect}
          title={<TabTitleText>Mapping Section</TabTitleText>}
          tabContentId="tabSection"
          tabContentRef={sectionItemsRef}
        />
        <Tab
          eventKey={2}
          isDisabled={modalVerb == 'POST' ? false : true}
          title={<TabTitleText>Existing</TabTitleText>}
          tabContentId="tabExistingTestSpecification"
          tabContentRef={existingItemsRef}
        />
      </Tabs>
      <div>
        <TabContent eventKey={0} id="tabNewTestSpecification" ref={newItemRef}>
          <TabContentBody hasPadding>
            <TestSpecificationForm
              api={api}
              formAction={modalAction}
              formData={modalFormData}
              formVerb={modalVerb}
              parentData={parentData}
              parentType={parentType}
              parentRelatedToType={parentRelatedToType}
              handleModalToggle={handleModalToggle}
              loadMappingData={loadMappingData}
              baseApiUrl={baseApiUrl}
              modalIndirect={modalIndirect}
              modalOffset={modalOffset}
              modalSection={modalSection}
            />
          </TabContentBody>
        </TabContent>
        <TabContent eventKey={1} id="tabSection" ref={sectionItemsRef} hidden>
          <TabContentBody hasPadding>
            <SectionForm
              api={api}
              formVerb={modalVerb}
              handleModalToggle={handleModalToggle}
              baseApiUrl={baseApiUrl}
              modalIndirect={modalIndirect}
              modalOffset={modalOffset}
              modalSection={modalSection}
              setModalOffset={setModalOffset}
              setModalSection={setModalSection}
            />
          </TabContentBody>
        </TabContent>
        <TabContent eventKey={2} id="tabExistingTestSpecification" ref={existingItemsRef} hidden>
          <TabContentBody hasPadding>
            <TestSpecificationSearch
            api={api}
            parentData={parentData}
            formVerb={modalVerb}
            parentData={parentData}
            parentType={parentType}
            parentRelatedToType={parentRelatedToType}
            handleModalToggle={handleModalToggle}
            loadMappingData={loadMappingData}
            baseApiUrl={baseApiUrl}
            modalIndirect={modalIndirect}
            modalOffset={modalOffset}
            modalSection={modalSection}
            />
          </TabContentBody>
        </TabContent>
      </div>

      </Modal>
    </React.Fragment>
  );
};
