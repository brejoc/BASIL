import React from 'react';
import { Form, FormGroup, HelperText, HelperTextItem, FormHelperText, Button, TextInput, ActionGroup, Hint, HintBody} from '@patternfly/react-core';
import {
  DataList,
  DataListItem,
  DataListCell,
  DataListItemRow,
  DataListItemCells,
  DataListAction,
  SearchInput,
} from '@patternfly/react-core';

export interface SwRequirementSearchProps {
  api;
  baseApiUrl: str;
  formDefaultButtons: int;
  formVerb: str;
  formAction: str;
  formData;
  formMessage: string;
  parentType: string;
  modalFormSubmitState: string;
  setModalFormSubmitState;
  handleModalToggle;
  modalOffset;
  modalSection;
  loadMappingData;
}

export const SwRequirementSearch: React.FunctionComponent<SwRequirementSearchProps> = ({
    api,
    baseApiUrl,
    formDefaultButtons= 1,
    formVerb='POST',
    formAction='add',
    formData = {'id': 0,
                'title': '',
                'description': ''},
    formMessage = "",
    parentType = "",
    modalFormSubmitState = "waiting",
    setModalFormSubmitState,
    handleModalToggle,
    modalOffset,
    modalSection,
    loadMappingData,
    }: SwRequirementSearchProps) => {

    const [searchValue, setSearchValue] = React.useState(formData.title);
    const [messageValue, setMessageValue] = React.useState(formMessage);
    const [statusValue, setStatusValue] = React.useState('waiting');
    const [swRequirements, setSwRequirements] = React.useState([]);
    const [selectedDataListItemId, setSelectedDataListItemId] = React.useState('');

    const [coverageValue, setCoverageValue] = React.useState(formData.coverage);
    const [validatedCoverageValue, setValidatedCoverageValue] = React.useState<validate>('error');

    const resetForm = () => {
        setSelectedDataListItemId(-1);
        setCoverageValue("0");
        setSearchValue("");
    }

    React.useEffect(() => {
        if (coverageValue === '') {
          setValidatedCoverageValue('default');
        } else if (/^\d+$/.test(coverageValue)) {
          if ((coverageValue >= 0) && (coverageValue <= 100)){
            setValidatedCoverageValue('success');
          } else {
            setValidatedCoverageValue('error');
          }
        } else {
          setValidatedCoverageValue('error');
        }
    }, [coverageValue]);

    const handleCoverageValueChange = (_event, value: string) => {
        setCoverageValue(value);
    };

    const onChangeSearchValue = (value) => {
      setSearchValue(value);
    }

    const onSelectDataListItem = (_event: React.MouseEvent | React.KeyboardEvent, id: string) => {
      setSelectedDataListItemId(id);
    };

    const handleInputChange = (_event: React.FormEvent<HTMLInputElement>, id: string) => {
      setSelectedDataListItemId(id);
    };

    React.useEffect(() => {
        loadSwRequirements(searchValue);
    }, [searchValue]);

    React.useEffect(() => {
        if (statusValue == 'submitted'){
          handleSubmit();
        }
    }, [statusValue]);

    const loadSwRequirements = (searchValue) => {
      let url = baseApiUrl + '/sw-requirements?search=' + searchValue;
      fetch(url)
        .then((res) => res.json())
        .then((data) => {
            setSwRequirements(data);
        })
        .catch((err) => {
          console.log(err.message);
        });
    }

    const getSwRequirementsTable = (sw_requirements) => {
      return sw_requirements.map((sw_requirement, srIndex) => (
        <DataListItem key={sw_requirement.id} aria-labelledby={"clickable-action-item-" + sw_requirement.id} id={sw_requirement.id}>
          <DataListItemRow>
            <DataListItemCells
              dataListCells={[
                <DataListCell key="primary content">
                  <span id={"clickable-action-item-" + sw_requirement.id}>{sw_requirement.title}</span>
                </DataListCell>,
              ]}
            />
            <DataListAction
              aria-labelledby={"clickable-action-item-" + sw_requirement.id + " clickable-action-action-" + sw_requirement.id}
              id={"clickable-action-action-" + sw_requirement.id}
              aria-label="Actions"
              isPlainButtonAction
            >
            </DataListAction>
          </DataListItemRow>
        </DataListItem>
      ))
    }

    const handleSubmit = () => {
        if ((selectedDataListItemId == -1) || (selectedDataListItemId == '') || (selectedDataListItemId == undefined)){
            setMessageValue('Please, select an item before submitting the form.');
            setStatusValue('waiting');
            return;
        } else if (validatedCoverageValue != 'success'){
            setMessageValue('Coverage of Parent Item is mandatory and must be a integer value in the range 0-100.');
            setStatusValue('waiting');
            return;
        } else if (modalSection.trim().length==0){
            setMessageValue('Section of the software component specification is mandatory.');
            setStatusValue('waiting');
            return;
        } else if (modalSection.trim().length==0){
            setMessageValue('Section of the software component specification is mandatory.');
            setStatusValue('waiting');
            return;
        }

        setMessageValue('');

        let data = {
          'api-id': api.id,
          'sw-requirement': {'id': selectedDataListItemId},
          'section': modalSection,
          'offset': modalOffset,
          'coverage': coverageValue,
        }

        if ((formVerb == 'PUT') || (formVerb == 'DELETE')){
          setMessageValue('Wrong actions.');
          setStatusValue('waiting');
          return;
        }

        fetch(baseApiUrl + '/mapping/api/sw-requirements', {
          method: formVerb,
          headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(data),
        })
          .then((response) => {
            if (response.status !== 200) {
              setMessageValue(response.statusText);
              setStatusValue('waiting');
            } else {
              setStatusValue('waiting');
              setMessageValue('Database updated!');
              handleModalToggle();
              setMessageValue('');
              loadMappingData();
            }
          })
          .catch((err) => {
            setStatusValue('waiting');
            setMessageValue(err.toString());
          });
      };

    return (
        <React.Fragment>
        <SearchInput
          placeholder="Search Identifier"
          value={searchValue}
          onChange={(_event, value) => onChangeSearchValue(value)}
          onClear={() => onChangeSearchValue('')}
          style={{width:'400px'}}
        />
        <br />
        <DataList
          isCompact
          aria-label="clickable data list example"
          selectedDataListItemId={selectedDataListItemId}
          onSelectDataListItem={onSelectDataListItem}
          onSelectableRowChange={handleInputChange}
        >
          {getSwRequirementsTable(swRequirements)}
        </DataList>
        <br />
        <FormGroup label="Unique Coverage:" isRequired fieldId={`input-sw-requirement-coverage-${formData.id}`}>
          <TextInput
            isRequired
            id={`input-sw-requirement-coverage-${formData.id}`}
            name={`input-sw-requirement-coverage-${formData.id}`}
            value={coverageValue || ''}
            onChange={(_ev, value) => handleCoverageValueChange(_ev, value)}
          />
          {validatedCoverageValue !== 'success' && (
            <FormHelperText>
              <HelperText>
                <HelperTextItem variant={validatedCoverageValue}>
                  {validatedCoverageValue === 'error' ? 'Must be an integer number in the range 0-100' : ''}
                </HelperTextItem>
              </HelperText>
            </FormHelperText>
          )}
        </FormGroup>
        <br />
          { messageValue ? (
          <Hint>
            <HintBody>
              {messageValue}
            </HintBody>
          </Hint>
          ) : (<span></span>)}

          {formDefaultButtons ? (
            <ActionGroup>
              <Button
                variant="primary"
                onClick={() => setStatusValue('submitted')}>
              Submit
              </Button>
              <Button
                variant="secondary"
                onClick={resetForm}>
                Reset
              </Button>
            </ActionGroup>
          ) : (<span></span>)}

        </React.Fragment>
   );
};
